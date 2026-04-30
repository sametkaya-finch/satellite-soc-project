import socket
import struct
import threading #ayni anda hem tcp hem udp portunu dinlemek icin 
import hmac     #imzalama nesnesi icin
import hashlib  #imzalama algoritmasi icin

#ag ayarlari
LISTEN_IP = "0.0.0.0" #tum ag arayuzleri dinleniyor
LISTEN_PORT = 5005    #makine1'in veri gonderdigi, makine2'nin isletim sisteminden isteyecegi port
TCP_PORT = 5006       #tcp heartbeat icin isletim sisteminden istenen port 

#anahtar (secret key)
SECRET_KEY = b"finch_ebg_atreides" #makine1 ve makine2nin bilecegi ortak gizli anahtar 

#threads arasi durum paylasimi icin bayrak 
tcp_connected = False

#seq numarasini tutacak (replay attack korumasi)
last_seq_id = -1 

def verify_and_unpack(data):

    payload = data[:24]            #ilk 24 byte gercek veri 
    received_signature = data[24:] #son 32 byte hmac izmasi 

    #gelen veriyi kullan ve ortak gizli anahtarla imza olustur 
    expected_signature = hmac.new(SECRET_KEY, payload, hashlib.sha256).digest()

    #imzalari karsilastir (== yerine compare_digest cunku hacker tarafindan yanlis olan bit tespit edilip dogrusu bulunabilir) 
    if not hmac.compare_digest(expected_signature, received_signature):
        raise ValueError("GECERSIZ IMZA (Spoofing/Manipulation Tespiti)")
    
    #gelen 24 bytelik veri tekrar eski haline getiriliyor 
    unpacked = struct.unpack('!Idfff', payload)
    
    return {
        "seq_id": unpacked[0],
        "timestamp": unpacked[1],
        "lat": unpacked[2],
        "lon": unpacked[3],
        "alt": unpacked[4]
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
                    #3 saniye icinde veri gelmezse yani ping gelmezse (tcp portuna ping atiliyordu) excepte duser
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
            
                #gelen veri 56byte ise yani cop veri degilse 
                if len(data) == 56:
                    try:
                        #imzayi dogrula her sey uygunsa 24bytelik veri donsun 
                        parsed_data = verify_and_unpack(data)

                        #replay attack korumasi 
                        current_seq = parsed_data['seq_id']

                        if current_seq <= last_seq_id:
                            print(f"[!] DROP (REPLAY ATTACK): Eski/Tekrar eden paket engellendi (SEQ: {current_seq})")
                            continue #paketi cope at bir sonraki pakete gec (donguye tekrar gir) 
                        
                        #her sey yolundaysa son okunan seq numarasini guncelle 
                        last_seq_id = current_seq

                        print(f"[<-] VERİ ALINDI | Kaynak IP: {addr[0]}")
                        print(f"    SEQ   : {parsed_data['seq_id']}")
                        print(f"    Enlem : {parsed_data['lat']:.4f}")
                        print(f"    Boylam: {parsed_data['lon']:.4f}")
                        print(f"    Irtifa: {parsed_data['alt']:.2f} km")
                        print("-" * 40)
                    except ValueError as e:
                        #imza dogrulanamazsa buraya duser 
                        print(f"[!] DROP (GUVENLIK): {e} | Kaynak IP: {addr[0]}")    
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