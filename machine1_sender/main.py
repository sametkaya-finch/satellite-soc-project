import requests
import ephem
import math
import time
import struct

#ISS TLE veri kaynagi 
TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=stations&FORMAT=tle"

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
            print(f"[+] Hedef Kilitlendi: {name}\n")
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
        
        #test icin 5 kez calisacak
        while sequence < 5:
            #uydunun anlik konumu enlem boylam yukseklik olarak doner
            sat_data = tracker.get_current_coordinates()
            
            #veri binary formata cevrildi 
            binary_packet = pack_telemetry_data(sequence, sat_data)
            
            #ekrana okunabilir bir sekilde ve hex formatinda basildi 
            print(f"[SEQ: {sequence}] Enlem: {sat_data['lat']:.4f}, Boylam: {sat_data['lon']:.4f}, Irtifa: {sat_data['alt']:.2f} km")
            print(f"Ham Bayt Ciktisi: {binary_packet.hex()}\n")
            
            sequence += 1

            #saniyede bir paket olmasi icin 
            time.sleep(1) 
            
    except Exception as e:
        print(f"[-] Sistem Hatasi: {e}")