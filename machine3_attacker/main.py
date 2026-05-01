from scapy.all import sniff, UDP, IP, Raw
import struct

#ag ayarlari

BPF_FILTER = "udp port 5005" #makine2'ye giden 5005 portundaki udp trafigini filtreler 
IFACE = "lo"  #loopback interface'i dinleniyor linuxta bu interface lo

def parse_intercepted_packet(packet):
    #paket udp ise ve raw katmani iceriyorsa 
    if packet.haslayer(UDP) and packet.haslayer(Raw):
        
        #veriyi al 
        raw_payload = packet[Raw].load
        
        #24 byte veri 32 byte imza mi kontrol 
        if len(raw_payload) == 56:
            data_part = raw_payload[:24]
            
            try:
                #veriyi cozelim 
                unpacked = struct.unpack('!Idfff', data_part)
                
                print(f"[!] GİZLİ DİNLEME | Kaynak IP: {packet[IP].src}")
                print(f"    Ele Gecirilen SEQ : {unpacked[0]}")
                print(f"    Sizdirilan Enlem  : {unpacked[2]:.4f}")
                print(f"    Sizdirilan Boylam : {unpacked[3]:.4f}")
                print(f"    HMAC İmza Durumu  : Okunamiyor (Şifreli)")
                print("-" * 50)
            except struct.error:
                print("[-] Paket formati uymuyor.")

if __name__ == "__main__":
    print("[*] Makine 3 (Hacker) aktif edildi...")
    print(f"[*] '{IFACE}' arayuzunde promiscuous modda (gizli) dinleme basladi.")
    print(f"[*] Hedef Filtre: {BPF_FILTER}\n")
    
    try:
        #yakalanan her paket icin prn'de belirtilen fonksiyon calistirilacak, store=0 ile yakalanan paketler ram'e kaydedilmeyecek
        sniff(iface=IFACE, filter=BPF_FILTER, prn=parse_intercepted_packet, store=0)
    except Exception as e:
        print(f"[-] Bektlenmeyen Hata: {e}")
    except PermissionError:
        print("[-] HATA: Scapy ag paketlerini yakalamak icin 'root' (sudo) yetkilerine ihtiyac duyar!")  
        print("Lutfen scripti 'sudo ../venv/bin/python main.py' seklinde calistirin.")
    except KeyboardInterrupt:
        print("\n[*] Sniffing durduruldu.")