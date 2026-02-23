# kafa_tespiti_youtube_akici.py
from ultralytics import YOLO
import cv2
import os
import yt_dlp
import sys
import time
from collections import deque

# ==================== KONFİGÜRASYON ====================
MODEL_ADI = 'medium.pt'
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"  # Tokyo yürüyüşü
# ========================================================

print("=" * 60)
print("📹 YOUTUBE CANLI YAYININDA KAFA TESPİTİ (AKICI)")
print("=" * 60)

# 1. Model kontrolü ve yükleme
if not os.path.exists(MODEL_ADI):
    print(f"❌ {MODEL_ADI} bulunamadı!")
    sys.exit()
else:
    print(f"✅ Model bulundu: {MODEL_ADI}")
    model = YOLO(MODEL_ADI)
    print("✅ Model yüklendi!")

# 2. YouTube akış linkini al
print(f"📡 YouTube'a bağlanılıyor...")
try:
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_URL, download=False)
        video_url = info['url']
        print(f"✅ Akış linki alındı: {info.get('title', 'Bilinmiyor')}")
except Exception as e:
    print(f"❌ Bağlantı hatası: {e}")
    sys.exit()

# 3. VideoCapture ayarları (BUFFER SIFIRLAMA!)
cap = cv2.VideoCapture(video_url)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Buffer'ı minimumda tut
cap.set(cv2.CAP_PROP_FPS, 30)        # FPS'i sabitle

if not cap.isOpened():
    print("❌ Video akışı açılamadı!")
    sys.exit()

print("✅ Canlı yayın başladı! Çıkmak için 'q'")
print("=" * 60)

# 4. Akıcılık için değişkenler
fps = 30
prev_time = 0
frame_sayacı = 0

# Son tespitleri tut (sabit görüntü için)
son_kafalar = deque(maxlen=5)
son_annotated = None

while True:
    # Zaman kontrolü (tam 30 fps)
    time_elapsed = time.time() - prev_time
    if time_elapsed < 1.0/fps:
        continue
    prev_time = time.time()
    
    # Kareyi al
    ret, frame = cap.read()
    if not ret:
        print("⚠️ Yayın kesildi, yeniden bağlanılıyor...")
        cap = cv2.VideoCapture(video_url)
        continue
    
    frame_sayacı += 1
    
    # Her 3 karede bir tespit yap (performans için)
    if frame_sayacı % 3 == 0:
        results = model(frame)
        kafa_sayisi = len(results[0].boxes)
        son_kafalar.append(kafa_sayisi)
        
        # Tespit edilenleri çiz
        annotated_frame = results[0].plot()
        
        # Sayıyı yaz (büyük ve sabit)
        cv2.putText(annotated_frame, f"KISI SAYISI: {kafa_sayisi}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        
        # Yayın bilgisi
        cv2.putText(annotated_frame, "YouTube Canli Yayin", (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        son_annotated = annotated_frame
    else:
        # Tespit yapılmayan karelerde son tespiti göster (SABİTLİK!)
        if son_annotated is not None:
            # Son tespit edilmiş kareyi göster
            display_frame = son_annotated
        else:
            # Henüz tespit yoksa ham görüntüyü göster
            display_frame = frame
            cv2.putText(display_frame, f"KISI SAYISI: HESAPLANIYOR...", (20, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    # Görüntüyü göster
    cv2.imshow('Kafa Tespiti (Akici)', display_frame)
    
    # 'q' ile çık
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Temizlik
cap.release()
cv2.destroyAllWindows()
print("\n👋 Program sonlandı.")