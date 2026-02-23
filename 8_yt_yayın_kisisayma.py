# kafa_tespiti_kabukicho.py
from ultralytics import YOLO
import cv2
import os
import yt_dlp
import sys
import time
from collections import deque

# ==================== KONFİGÜRASYON ====================
MODEL_ADI = 'yolov8n.pt'
# Tokyo Kabukicho 24/7 Canlı Yayın
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"
# ========================================================

print("=" * 60)
print("📹 KABUKICHO CANLI YAYININDA KİŞİ SAYACI")
print("=" * 60)

# 1. Model kontrolü
if not os.path.exists(MODEL_ADI):
    print(f"❌ {MODEL_ADI} bulunamadı!")
    print("   Lütfen medium.pt dosyasını bu klasöre kopyalayın.")
    sys.exit()
else:
    print(f"✅ Model bulundu: {MODEL_ADI} ({os.path.getsize(MODEL_ADI)} bytes)")

# 2. Modeli yükle
print("🔄 Model yükleniyor...")
model = YOLO(MODEL_ADI)
print("✅ Model yüklendi!")

# 3. YouTube canlı yayın akışını al
print(f"📡 Tokyo Kabukicho canlı yayınına bağlanılıyor...")
print(f"🔗 URL: {YOUTUBE_URL}")

try:
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(YOUTUBE_URL, download=False)
        video_url = info['url']
        print(f"✅ Akış linki alındı!")
        print(f"📊 Yayın başlığı: {info.get('title', 'Bilinmiyor')}")
except Exception as e:
    print(f"❌ YouTube'a bağlanılamadı: {e}")
    print("   İnternet bağlantını kontrol et veya URL'yi dene.")
    sys.exit()

# 4. VideoCapture ayarları (AKICI OLMASI İÇİN)
cap = cv2.VideoCapture(video_url)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)       # Buffer'ı minimumda tut
cap.set(cv2.CAP_PROP_FPS, 30)             # FPS'i sabitle

if not cap.isOpened():
    print("❌ Video akışı açılamadı!")
    sys.exit()

print("✅ Canlı yayına bağlandı! (Tokyo - Kabukicho)")
print("🎥 Çıkmak için 'q' tuşuna basın.")
print("=" * 60)

# 5. Akıcılık ve sabitlik için değişkenler
fps = 30
prev_time = 0
frame_sayacı = 0
son_kisiler = deque(maxlen=5)  # Son 5 tespiti tut (dalgalanmayı azalt)

# Son görüntü (sabit göstermek için)
son_goruntu = None

while True:
    # Zaman kontrolü (tam 30 fps'de kal)
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
        # KİŞİ TESPİTİ YAP (kafa modeliyle)
        results = model(frame)
        kisi_sayisi = len(results[0].boxes)
        
        # Son sayıları kuyruğa ekle (dalgalanmayı azalt)
        son_kisiler.append(kisi_sayisi)
        
        # Kararlı sayı (medyan ile)
        kararli_sayi = int(sorted(son_kisiler)[len(son_kisiler)//2]) if son_kisiler else 0
        
        # Tespit edilenleri çiz
        son_goruntu = results[0].plot()
        
        # Sayıyı yaz (büyük ve yeşil)
        cv2.putText(son_goruntu, f"KISI SAYISI: {kararli_sayi}", (30, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
        
        # Anlık sayı ve konum bilgisi (daha küçük)
        cv2.putText(son_goruntu, f"(anlik: {kisi_sayisi})", (30, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        
        # Yayın bilgisi
        cv2.putText(son_goruntu, "Tokyo - Kabukicho Canli", (30, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 1)
        
        # Zaman damgası
        cv2.putText(son_goruntu, time.strftime("%H:%M:%S"), (30, 160),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Gösterilecek görüntüyü güncelle
        display_frame = son_goruntu
    else:
        # Tespit yapılmayan karelerde son tespit edilmiş görüntüyü göster
        if son_goruntu is not None:
            display_frame = son_goruntu
        else:
            # Henüz tespit yoksa ham görüntüyü göster
            display_frame = frame
            cv2.putText(display_frame, "KISI SAYISI: HESAPLANIYOR...", (30, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    
    # Görüntüyü göster
    cv2.imshow('Kabukicho Canli Kisi Sayaci', display_frame)
    
    # 'q' tuşu ile çık
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 6. Temizlik
cap.release()
cv2.destroyAllWindows()
print("\n👋 Program sonlandırıldı.")
print(f"📊 İşlenen kare sayısı: {frame_sayacı}")