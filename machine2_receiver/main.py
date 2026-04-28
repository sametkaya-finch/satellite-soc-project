import socket
import struct

#ag ayarlari
LISTEN_IP = "0.0.0.0" #tum ag arayuzleri dinleniyor
LISTEN_PORT = 5005    #makine1'in veri gonderdigi, makine2'nin isletim sisteminden isteyecegi port

def unpack_telemetry_data(binary_data):
    
    #gelen 24 bytelik veri tekrar eski haline getiriliyor 
    unpacked = struct.unpack('!Idfff', binary_data)
    
    return {
        "seq_id": unpacked[0],
        "timestamp": unpacked[1],
        "lat": unpacked[2],
        "lon": unpacked[3],
        "alt": unpacked[4]
    }

if __name__ == "__main__":
    #udp soketi (nesnesi) olusturuluyor ve 5005 portu dinleniyor 
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((LISTEN_IP, LISTEN_PORT))
    
    print(f"[*] Makine 2 Dinlemede... Beklenen Port: {LISTEN_PORT}\n")
    
    try:
        #surekli dinleme modunda kalacak
        while True:
            #revform ile gelen data ve gonderen ip adresi alinir. kesin 24 byte gelecegi icin 24 yazildi.
            #daha yuksek yazilabilirdi. veri 24byte oldugu icin dataya yine 24 yazilirdi.
            data, addr = sock.recvfrom(24)
            
            #gelen veri 24byte ise yani cop veri degilse 
            if len(data) == 24:
                parsed_data = unpack_telemetry_data(data)
                print(f"[<-] VERİ ALINDI | Kaynak IP: {addr[0]}")
                print(f"    SEQ   : {parsed_data['seq_id']}")
                print(f"    Enlem : {parsed_data['lat']:.4f}")
                print(f"    Boylam: {parsed_data['lon']:.4f}")
                print(f"    Irtifa: {parsed_data['alt']:.2f} km")
                print("-" * 40)
            else:
                print(f"[!] Dikkat: Gecersiz boyutta paket geldi ({len(data)} byte)")
                
    except KeyboardInterrupt:
        print("\n[*] Kullanici tarafindan dinleme durduruldu (Ctrl+C).")
    finally:
        #isletim sisteminden istenen 5005 nolu port serbest birakiliyor
        sock.close()