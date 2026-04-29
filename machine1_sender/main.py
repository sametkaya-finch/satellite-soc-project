import requests
import ephem
import math
import time
import struct
import socket

#ISS TLE veri kaynagi 
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"

#ag ayarlari
TARGET_IP = "127.0.0.1" #localhost
TARGET_PORT = 5005      #makine2'nin dinleyecegi, bizim verileri gonderecegimiz port
TCP_PORT = 5006         #makine2'nin dinlyecegi tcp portu 

class SatelliteTracker:
    def __init__(self):
        print("[*] CelesTrak API'den TLE verisi cekiliyor...")
        response = requests.get(TLE_URL)
        
        if response.status_code == 200:
            lines = response.text.strip().split('\n')

            #verinin text kismindaki ilk 3 satir kaydediliyor 
            name = lines[0].strip()
            tle1 = lines[1].strip()
            tle2 = lines[2].strip()
            
            #bu uc satir cozumleniyor ve kepler elemanlari elde ediliyor 
            self.sat = ephem.readtle(name, tle1, tle2)
            print(f"[+] Hedef Kilitlendi: {name}")
        else:
            raise Exception("API Baglanti Hatasi! CelesTrak'a ulasilamiyor.")

    def get_current_coordinates(self):
        
        #sistem saati ile kepler elemanlarindaki verinin alinma saati cikarilip enlem boylam ve irtifa bilgileri elde ediliyor 
        self.sat.compute(ephem.now())
        
        #enlem boylam radyan oldugu icin dereceye cevriliyor 
        lat = math.degrees(self.sat.sublat)
        lon = math.degrees(self.sat.sublong)
        
        #irtifa m oldugu icin km'ye cevriliyor 
        alt = self.sat.elevation / 1000.0 
        
        return {"lat": lat, "lon": lon, "alt": alt}

def pack_telemetry_data(seq_id, data):
    timestamp = time.time()

    #!Idfff formati: Unsigned Int(4), Double(8), Float(4), Float(4), Float(4) = 24 Byte
    payload = struct.pack('!Idfff', seq_id, timestamp, data['lat'], data['lon'], data['alt'])
    
    return payload

if __name__ == "__main__":
    try:
        #uydu takip nesnesi baslatiliyor ve kepler elemanlari (yorunge parametreleri) elde ediliyor
        tracker = SatelliteTracker()
        sequence = 0

        #udp soketi (nesnesi) olusturuluyor (ipv4 ve udp kullanilacagi belirtildi) 
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[*] UDP Soketi acildi. Hedef: {TARGET_IP}:{TARGET_PORT}")

        #tcp baglanti durumunu tutan bayrak 
        tcp_connected = False
        tcp_sock = None

        #donguye girmeden tcp baglantisi kuruluyor
        try:
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_sock.settimeout(1)
            tcp_sock.connect((TARGET_IP, TCP_PORT))
            tcp_connected = True
            print(f"[+] TCP Heartbeat BAGLANDI! ({TARGET_IP}:{TCP_PORT})\n")
        except Exception:
            print("[!] TCP Baglantisi yok, Makine 2 araniyor...")
        
        #test icin 10 kez calisacak
        while sequence < 10:
            #uydunun anlik konumu enlem boylam yukseklik olarak doner
            sat_data = tracker.get_current_coordinates()
            
            #veri binary formata cevrildi 
            binary_packet = pack_telemetry_data(sequence, sat_data)

            #olusturulan 24byte'lik veri aga basiliyor 
            sock.sendto(binary_packet, (TARGET_IP, TARGET_PORT))

            #tcp heartbeat 
            if not tcp_connected:
                try:
                    #bagli degilsek yeni bir soket (tcp nesnesi) olustur ve baglanmayi dene 
                    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    tcp_sock.settimeout(1) #baglanmasi icin 1 saniye ver 1 saniye sonra yanit gelmezse hata ver ve devam et
                    tcp_sock.connect((TARGET_IP, TCP_PORT))
                    tcp_connected = True
                    print(f"[+] TCP Heartbeat BAGLANDI! ({TARGET_IP}:{TCP_PORT})\n")
                except Exception:
                    print("[!] TCP Baglantisi yok, Makine 2 araniyor...")
            
            if tcp_connected:
                try:
                    #eger bagliysak ping at (ping yerine istedigini yazabilirsin)
                    tcp_sock.sendall(b"PING")
                except Exception as e:
                    #ping gittiginde ack gelmezse yani baglanti koptuysa 
                    print(f"[!] TCP KOPTU! Makine 2 yanit vermiyor. UDP körleme atiliyor...")
                    tcp_connected = False
                    if tcp_sock: 
                        tcp_sock.close() #kopan soketi temizle yeni soket nesnesi olusturulacak 

            #ekrana okunabilir bir sekilde basildi
            print(f"[SEQ: {sequence}] Enlem: {sat_data['lat']:.4f}, Boylam: {sat_data['lon']:.4f}, Irtifa: {sat_data['alt']:.2f} km")
            print(f"[->] GÖNDERİLDİ | SEQ: {sequence} | Boyut: {len(binary_packet)} byte")
            
            sequence += 1

            #saniyede bir paket olmasi icin 
            time.sleep(1) 
            
    except Exception as e:
        print(f"[-] Sistem Hatasi: {e}")
    finally:
        #program bitince ya da sock nesnesi olusmus ve bir hata meydana gelirse socketi kapat portu serbest birak 
        #bu port 5005 numarali port degil veriyi gonderdigimiz makine1 icin ayrilmis portu kapatiyoruz
        if 'sock' in locals():
            sock.close()    
        if 'tcp_sock' in locals(): 
            tcp_sock.close() #tcp portu da kapaniyor 