# Satellite SOC & Anomaly Detection System

Bu proje, uydu telemetri verilerini UDP üzerinden ikili (binary) formatta aktaran, HMAC-SHA256 ile imzalayan ve saldırı tespitini L4 (Kural Tabanlı) ile L7 (LSTM Zaman Serisi YSA) katmanlarında yapan bir ağ güvenliği simülasyonudur.

## Modüller
* **Makine 1:** Telemetri Kaynağı (UDP/TCP, Struct Binary Packing)
* **Makine 2:** Doğrulama ve LSTM Karar Motoru
* **Makine 3:** Tehdit Aktörü (Scapy, Sızma Testi Vektörleri)
* **Makine 4:** SOC Dashboard (WebSocket, HTML/JS Arayüzü)
