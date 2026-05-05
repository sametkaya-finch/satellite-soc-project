import socket
import struct
import threading #ayni anda hem tcp hem udp portunu dinlemek icin 
import hmac      #imzalama nesnesi icin
import hashlib   #imzalama algoritmasi icin
import time      #rate limiting icin eklendi 
import requests  #makine4'e http istegi atmak icin 
import numpy as np
import joblib
from collections import deque
import os
import tensorflow as tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2' #tf uyarilarini gizle
from tensorflow.keras.models import load_model

#ysa modeli ve scaler yukleniyor
print("[*] YSA Modeli ve Scaler yukleniyor...")
scaler = joblib.load('scaler.pkl')
model  = load_model('model.h5')

#kayan pencere (sliding window) tamponu
TIME_STEPS = 30
NUM_FEATURES = 5
window_buffer = deque(maxlen=TIME_STEPS)

#sinif etiketleri
CLASS_NAMES = ['NORMAL', 'SPOOF', 'DRIFT', 'JITTER']

#tf graph isitma (warm-up): ilk tahmin isleminin (inference) gecikme latency'sini onlemek icin
dummy_data = np.zeros((1, TIME_STEPS, NUM_FEATURES))
model.predict(dummy_data, verbose=0)
print("[+] YSA Cikarim Motoru (Inference Engine) Hazir.\n")

#ag ayarlari
LISTEN_IP   = "0.0.0.0"  #tum ag arayuzleri dinleniyor
LISTEN_PORT = 5005       #makine1'in veri gonderdigi, makine2'nin isletim sisteminden isteyecegi port
TCP_PORT    = 5006       #tcp heartbeat icin isletim sisteminden istenen port

#anahtar (secret key)
SECRET_KEY = os.environ.get("SECRET_KEY", "finch_ebg_atreides").encode() #makine1 ve makine2nin bilecegi ortak gizli anahtar

#makine4 (soc) api adresi
MAKINE4_API = "http://172.20.0.5:8000/api/telemetry"

#threads arasi durum paylasimi icin bayrak
tcp_connected = False

#seq numarasini tutacak (replay attack korumasi)
last_seq_id = -1

prev_lat = None
prev_lon = None

#dos tespiti (rate limiter) icin sayac degiskenleri
paket_sayaci       = 0
son_sifirlama_zamani = time.time()
dos_baslangic_zamani = None   #dos'un ne zaman basladigini tutar
dos_aktif            = False  #dos devam ediyor mu


#verileri ve alarmlari makine4'e ileten fonksiyon
def send_to_soc(data_dict):
    try:
        requests.post(MAKINE4_API, json=data_dict, timeout=0.5)
    except Exception:
        pass #makine4 kapaliysa makine2 kilitlenmesin diye


def verify_and_unpack(data):

    payload            = data[:24]  #ilk 24 byte gercek veri
    received_signature = data[24:]  #son 32 byte hmac imzasi

    #gelen veriyi kullan ve ortak gizli anahtarla imza olustur
    expected_signature = hmac.new(SECRET_KEY, payload, hashlib.sha256).digest()

    #imzalari karsilastir (== yerine compare_digest cunku hacker tarafindan yanlis olan bit tespit edilip dogrusu bulunabilir)
    if not hmac.compare_digest(expected_signature, received_signature):
        raise ValueError("GECERSIZ IMZA (Spoofing/Manipulation Tespiti)")

    #gelen 24 bytelik veri tekrar eski haline getiriliyor
    unpacked = struct.unpack('!Idfff', payload)

    return {
        "seq_id":    unpacked[0],
        "timestamp": unpacked[1],
        "lat":       unpacked[2],
        "lon":       unpacked[3],
        "alt":       unpacked[4]
    }


#makine1'den gelen tcp ping sinyallerini dinler
def tcp_heartbeat_listener():
    global tcp_connected #bayraga erisim izni

    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.bind((LISTEN_IP, TCP_PORT))
    tcp_sock.listen(1)
    print(f"[*] TCP Heartbeat Dinlemede... Port: {TCP_PORT}")

    while True:
        try:
            conn, addr = tcp_sock.accept()
            print(f"[+] TCP Baglantisi Kuruldu: {addr[0]}\n")
            tcp_connected = True #tcp baglantisi kuruldu

            #donanimsal kesintiler icin kernele 3 saniyelik limit.
            conn.settimeout(3.0)

            while True:
                try:
                    #ping datasi. ping 4 karakterli o yuzden 4byte
                    #3 saniye icinde veri gelmezse yani ping gelmezse excepte duser
                    data = conn.recv(4)

                    #veri geldi ama bos b"" o halde makine1 normal bir sekilde kapatilmistir
                    if not data:
                        break #finally'e atla

                except socket.timeout:
                    print(f"[!] TCP ZAMAN ASIMI: {addr[0]} makinesinden PING alinamiyor!")
                    break #finally'e atla

        except Exception as e:
            print(f"[!] TCP Baglantisi Koptu: {e}")

        finally:
            #baglantinin koptugunu bildir
            tcp_connected = False
            if 'conn' in locals():
                conn.close() #soketi kapat
            print("[-] TCP Baglantisi Kapatildi, Yeni baglanti bekleniyor...\n")


if __name__ == "__main__":

    #main thread udp yeni thread tcp_heartbeat_listener
    tcp_thread = threading.Thread(target=tcp_heartbeat_listener, daemon=True)
    tcp_thread.start()

    #udp soketi (nesnesi) olusturuluyor ve 5005 portu dinleniyor
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))

    #soket icin 2 saniye konfigure ediliyor
    sock.settimeout(2.0)

    print(f"[*] Makine 2 Dinlemede... Beklenen Port: {LISTEN_PORT}")

    try:
        #surekli dinleme modunda kalacak
        while True:
            try:
                #recvform ile gelen data ve gonderen ip adresi alinir. 56byte (24 veri + 32 hmac) gelecek
                #2 saniye icinde veri gelmezse excepte duser
                data, addr = sock.recvfrom(56)

                #dos rate limiter 
                su_an = time.time()

                if su_an - son_sifirlama_zamani > 1.0:
                    #bir onceki saniyede paket sayisi normale dondusse dos bitmis demektir; tek satir bitis logu basilir
                    if dos_aktif and paket_sayaci <= 10:
                        sure = max(0.0, (su_an - dos_baslangic_zamani) - 1.0)
                        msg  = f"[BİLGİ] DoS SONA ERDİ. Toplam sure: {sure:.1f}s"
                        print(f"[+] {msg}")
                        send_to_soc({"type": "alert", "message": msg})
                        dos_aktif            = False
                        dos_baslangic_zamani = None

                    paket_sayaci         = 0
                    son_sifirlama_zamani = su_an

                paket_sayaci += 1

                if paket_sayaci > 10: #saniyede 10 paketten fazlasi dos demektir
                    #dos_aktif False iken (dos yeni basladiysa) tek seferlik log basilir
                    #bayrak True olduktan sonra bu blok sessizce continue eder konsol spam olmaz
                    if not dos_aktif:
                        dos_aktif            = True
                        dos_baslangic_zamani = time.time()
                        msg = "[KRİTİK] DoS FLOOD TESPİT EDİLDİ!"
                        print(f"[!] DROP (RATE LIMIT): {msg}")
                        send_to_soc({"type": "alert", "message": msg})
                    continue #paketi dogrudan cope at, l7'ye (ysa'ya) gitmeden biter

                #imza + seq dogrulamasi 
                if len(data) == 56:
                    try:
                        #imzayi dogrula her sey uygunsa 24bytelik veri donsun
                        parsed_data = verify_and_unpack(data)

                        #replay attack / out-of-order korumasi
                        current_seq  = parsed_data['seq_id']
                        paket_zamani = parsed_data['timestamp'] #paketin uretim zamani

                        if current_seq <= last_seq_id:
                            if not dos_aktif:
                                msg = f"[UYARI] Eski/Tekrar eden paket engellendi (SEQ: {current_seq})"
                                print(f"[!] DROP (OUT-OF-ORDER): {msg}")
                                send_to_soc({"type": "alert", "message": msg})
                            continue #paketi cope at, ysa'ya gitmesin

                        #her sey yolundaysa son okunan seq numarasini guncelle
                        last_seq_id = current_seq

                        delta = max(0.0, time.time() - paket_zamani)

                        lat_diff = (parsed_data['lat'] - prev_lat) if prev_lat is not None else 0.0
                        lon_diff = (parsed_data['lon'] - prev_lon) if prev_lon is not None else 0.0
                        prev_lat = parsed_data['lat']
                        prev_lon = parsed_data['lon']

                        window_buffer.append([
                            parsed_data['lat'],
                            parsed_data['lon'],
                            parsed_data['alt'],
                            delta,
                            lat_diff,
                            lon_diff,
                        ])

                        ysa_karari_str    = "ANALIZ_BEKLENIYOR"
                        guven_skoru_float = 0.0

                        #tampon 50 pakete ulastiginda model predict calistir
                        if len(window_buffer) == TIME_STEPS:
                            raw_window = np.array(window_buffer)  # (30, 6)
 
                            x_idx = np.arange(TIME_STEPS)
 
                            lat_fit     = np.polyfit(x_idx, raw_window[:, 0], 1)
                            lat_res_std = np.std(raw_window[:, 0] - np.polyval(lat_fit, x_idx))
 
                            lon_fit     = np.polyfit(x_idx, raw_window[:, 1], 1)
                            lon_res_std = np.std(raw_window[:, 1] - np.polyval(lon_fit, x_idx))
 
                            lat_res_col = np.full((TIME_STEPS, 1), lat_res_std)
                            lon_res_col = np.full((TIME_STEPS, 1), lon_res_std)
 
                            full_window = np.concatenate([
                                raw_window[:, 3:4], 
                                raw_window[:, 4:5], 
                                raw_window[:, 5:6], 
                                lat_res_col, 
                                lon_res_col
                            ], axis=1)
                            
                            scaled_window = scaler.transform(full_window)
                            tensor_input  = np.expand_dims(scaled_window, axis=0)  # (1, 50, 8)

                            #cikarim (inference)
                            predictions          = model.predict(tensor_input, verbose=0)
                            predicted_class_idx  = np.argmax(predictions, axis=1)[0]

                            ysa_karari_str    = CLASS_NAMES[predicted_class_idx]
                            guven_skoru_float = round(float(predictions[0][predicted_class_idx]) * 100, 2)

                            print(f"[AI] Model Karari: {ysa_karari_str} | Guven: %{guven_skoru_float}")

                        print(f"[<-] VERI ALINDI | SEQ: {parsed_data['seq_id']} | Kaynak IP: {addr[0]}")

                        send_to_soc({
                            "type":            "telemetry",
                            "seq":             parsed_data['seq_id'],
                            "lat":             parsed_data['lat'],
                            "lon":             parsed_data['lon'],
                            "alt":             parsed_data['alt'],
                            "paket_timestamp": paket_zamani,
                            "delta":           round(delta, 4),
                            "ysa_karari":      ysa_karari_str,
                            "guven_skoru":     guven_skoru_float
                        })

                    except ValueError as e:
                        #imza dogrulanamazsa buraya duser
                        msg = f"{e} | Kaynak IP: {addr[0]}"
                        print(f"[!] DROP (GUVENLIK): {msg}")
                        send_to_soc({"type": "alert", "message": msg})
                else:
                    print(f"[!] Dikkat: Gecersiz boyutta paket geldi ({len(data)} byte)")

            except socket.timeout:
                #tcp bagli ise udp ile veri gelmesinde bir problem vardir, tcp de yoksa tum baglanti kopmustur
                if tcp_connected:
                    print("[!] UYARI: UDP Telemetri verisi gecikiyor, ancak Makine 1 (TCP) hala hayatta!")
                else:
                    print("[!] KRİTİK: Makine 1 ile tüm iletisim (TCP ve UDP) kesildi. Veri akisi durdu!")

    except KeyboardInterrupt:
        print("\n[*] Kullanici tarafindan dinleme durduruldu (Ctrl+C).")
    finally:
        #isletim sisteminden istenen 5005 nolu port serbest birakiliyor
        sock.close()