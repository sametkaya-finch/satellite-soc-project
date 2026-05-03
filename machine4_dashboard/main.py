from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import socket
import csv
import os
import time
from datetime import datetime
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app = FastAPI()

#cors ayarlari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_dashboard():
    return FileResponse("index.html")

MAKINE3_CMD_PORT = 5007
CSV_FILE = "dataset.csv"

#csv dosyasi yoksa olustur ve basliklarini yaz
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "seq", "lat", "lon", "alt", "delta", "label"])

connected_clients = []
current_label = 0

LABEL_MAP = {
    "NORMAL":        0,
    "SPOOF":         1,
    "DRIFT":         2,
    "JITTER":        3,
    "OUT_OF_ORDER":  4,
    "DOS":           5
}


class TelemetryData(BaseModel):
    type:             str
    seq:              Optional[int]   = None
    lat:              Optional[float] = None
    lon:              Optional[float] = None
    alt:              Optional[float] = None
    paket_timestamp:  Optional[float] = None
    # m2'nin gonderdigi delta gurultudan arindirilmis temiz degerdir
    delta:            Optional[float] = None
    message:          Optional[str]   = None
    ysa_karari:       Optional[str]   = None
    guven_skoru:      Optional[float] = None


#c&c api: arayuzden gelen saldiri komutlarini makine3'e iletir ve etiketi gunceller
@app.post("/api/command/{attack_type}")
async def send_command(attack_type: str):
    global current_label
    try:
        if attack_type in LABEL_MAP:
            current_label = LABEL_MAP[attack_type]
        else:
            return {"status": "error", "details": "Gecersiz saldiri turu"}

        cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cmd_sock.connect(("127.0.0.1", MAKINE3_CMD_PORT))
        cmd_sock.sendall(attack_type.encode())
        cmd_sock.close()

        print(f"[+] Saldiri Emri Verildi: {attack_type} (Etiket: {current_label})")
        return {"status": "success", "command": attack_type, "current_label": current_label}

    except ConnectionRefusedError:
        return {"status": "error", "details": "Makine 3'e baglanilamamadi."}
    except Exception as e:
        return {"status": "error", "details": str(e)}


#veri toplama ve yayin merkezi
@app.post("/api/telemetry")
async def receive_telemetry(data: TelemetryData):
    #gelen veri temiz telemetri ise csv'ye yaz
    if data.type == "telemetry":
        delta_yazilacak = data.delta if data.delta is not None else 0.0

        with open(CSV_FILE, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                data.seq,
                data.lat,
                data.lon,
                data.alt,
                round(delta_yazilacak, 4),
                current_label
            ])

    #gelen veriyi tum bagli ws istemcilerine yayinla (telemetri ve alert)
    json_data = data.model_dump_json()
    for client in connected_clients:
        try:
            await client.send_text(json_data)
        except Exception:
            pass

    return {"status": "success"}


#ws canli yayin: dashboard istemcilerini yonetir
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        while True:
            await websocket.receive_bytes()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)


if __name__ == "__main__":
    print("="*50)
    print(" MAKINE 4: SOC DASHBOARD VE YSA VERİ TOPLAMA MERKEZİ")
    print("="*50)
    print("[*] API ve WebSocket port 8000 uzerinde dinleniyor...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")