//harita 
const map = L.map('map').setView([0, 0], 3);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO'
}).addTo(map);

//uydu ikonu 
const satMarker = L.circleMarker([0, 0], {
    color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.8, radius: 6
}).addTo(map);

//grafik ayarlari 
Chart.defaults.color = '#9ca3af';
Chart.defaults.font.family = "'Courier New', Courier, monospace";

//ortak grafik ayarlari 
const commonOptions = {
    responsive: true, maintainAspectRatio: false,
    animation: { duration: 0 },
    scales: {
        x: { display: false },
        y: { grid: { color: '#1f2937' } }
    },
    plugins: { legend: { display: true, labels: { color: '#f3f4f6' } } }
};

//delta grafigi 
const ctxDelta = document.getElementById('deltaChart').getContext('2d');
const deltaChart = new Chart(ctxDelta, {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'Ağ Gecikmesi (ms)', data: [], borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0 }] },
    options: commonOptions
});

//irtifa grafigi 
const ctxAlt = document.getElementById('altChart').getContext('2d');
const altChart = new Chart(ctxAlt, {
    type: 'line',
    data: { labels: [], datasets: [{ label: 'İrtifa (km)', data: [], borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.1)', borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0 }] },
    options: commonOptions
});

//grafiklere veri ekleme 
function updateChart(chart, label, dataPoint) {
    chart.data.labels.push(label);
    chart.data.datasets[0].data.push(dataPoint);
    if (chart.data.labels.length > 30) {
        chart.data.labels.shift();
        chart.data.datasets[0].data.shift();
    }
    chart.update();
}

//websocket baglantisi 
const ws = new WebSocket("ws://127.0.0.1:8000/ws");
const logBox = document.getElementById("siem-logs");

ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    if (data.type === "telemetry") {
        //harita guncelleme 
        satMarker.setLatLng([data.lat, data.lon]);
        map.panTo([data.lat, data.lon], {animate: true, duration: 0.5});
        
        //panel text guncellemesi 
        document.getElementById('t-seq').innerText = data.seq;
        document.getElementById('t-alt').innerText = data.alt.toFixed(2);
        document.getElementById('t-lat').innerText = data.lat.toFixed(4);
        document.getElementById('t-lon').innerText = data.lon.toFixed(4);
        
        //siem log 
        const timeStr = new Date().toLocaleTimeString();
        logBox.innerHTML += `<div class="log-entry log-safe">[${timeStr}] [L4 ONAYLI] SEQ: ${data.seq} | Veri İşlendi.</div>`;

        //grafikleri guncelle 
        if (data.paket_timestamp) {
            const currentTimeSec = Date.now() / 1000;
            let deltaMs = (currentTimeSec - data.paket_timestamp) * 1000;
            if (deltaMs < 0) deltaMs = 0;
            updateChart(deltaChart, data.seq, deltaMs);
        }
        updateChart(altChart, data.seq, data.alt);

        //ysa entegrasyonu ve XAI 
        const ysaDecision = document.getElementById('ysa-decision');
        const confidenceText = document.getElementById('confidence-text');
        const confidenceBar = document.getElementById('confidence-bar');
        const timeline = document.getElementById('timeline');
        const xaiBox = document.getElementById('xai-box');
        const xaiReason = document.getElementById('xai-reason');

        //makine2'den gelen ysa karari 
        const karar = data.ysa_karari || "ANALIZ_BEKLENIYOR";
        const skor = data.guven_skoru || 0;

        let boxClass = "box-unknown";

        if (karar === "ANALIZ_BEKLENIYOR") {
            ysaDecision.innerText = "BEKLENİYOR...";
            ysaDecision.style.color = "var(--text-muted)";
            confidenceBar.className = "progress-fill";
            confidenceBar.style.backgroundColor = "var(--border-dark)";
            xaiReason.innerText = "Tampon doluyor (30 paket gerekli). Lütfen bekleyin...";
            xaiBox.style.borderLeftColor = "var(--text-muted)";
        } 
        else if (karar === "NORMAL") {
            ysaDecision.innerText = "TEMİZ (NORMAL)";
            ysaDecision.style.color = "var(--neon-green)";
            confidenceBar.className = "progress-fill safe-fill";
            boxClass = "box-normal";
            
            xaiBox.style.borderLeftColor = "var(--neon-green)";
            xaiReason.innerText = "Tüm ağ metrikleri (İrtifa, Konum, Ağ Gecikmesi) nominal tolerans değerleri içerisindedir.";
        } 
        else {
            //saldiri durumu 
            ysaDecision.innerText = `ANOMALİ: ${karar}`;
            ysaDecision.style.color = "var(--neon-red)";
            confidenceBar.className = "progress-fill alert-fill";
            xaiBox.style.borderLeftColor = "var(--neon-red)";
            
            if (karar === "SPOOF") {
                boxClass = "box-spoof";
                xaiReason.innerText = "YSA (Stacked GRU): Koordinat ve irtifa verilerinde fizik kurallarına aykırı, açıklanamaz bir ani sıçrama (uzamsal anomali) tespit etti.";
            } 
            else if (karar === "DRIFT") {
                boxClass = "box-drift";
                xaiReason.innerText = "YSA (Stacked GRU): Zaman serisi boyunca uydunun rotasında istikrarlı ve birikimli bir mikro-sapma (yörünge kayması) eğilimi saptadı.";
            } 
            else if (karar === "JITTER") {
                boxClass = "box-jitter";
                xaiReason.innerText = "YSA (Stacked GRU) : Uzamsal veriler normal olmasına rağmen, paket varış sürelerinde (Delta metriği) düzensiz ağ gecikmeleri ve zamanlama anomalisi yakaladı.";
            }
        }

        confidenceText.innerText = skor + "%";
        confidenceBar.style.width = skor + "%";

        //heatmap 
        const newBox = document.createElement('div');
        newBox.className = `timeline-box ${boxClass}`;
        timeline.appendChild(newBox);

        if (timeline.children.length > 50) {
            timeline.removeChild(timeline.firstChild);
        }
    } 
    else if (data.type === "alert") {
        //dos ve out of order loglari 
        const timeStr = new Date().toLocaleTimeString();
        logBox.innerHTML += `<div class="log-entry log-alert">[${timeStr}] [L4 ENGEL] ${data.message}</div>`;
    }
    
    logBox.scrollTop = logBox.scrollHeight;
};

//api komut gonderimi 
function sendCommand(attackType) {
    fetch(`http://127.0.0.1:8000/api/command/${attackType}`, { method: 'POST' })
    .then(response => response.json())
    .then(data => {
        document.getElementById('current-mode').innerText = attackType;
        if(attackType === 'NORMAL') {
            document.getElementById('current-mode').style.color = 'var(--neon-green)';
        } else {
            document.getElementById('current-mode').style.color = 'var(--neon-red)';
        }
    })
    .catch(error => console.error('API Hatası:', error));
}