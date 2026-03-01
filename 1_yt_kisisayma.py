# main.py
import cv2
import subprocess
import numpy as np
from ultralytics import YOLO
import time
from collections import deque
from datetime import datetime
import yt_dlp
import os
import signal
import sys
from database import DatabaseManager

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ==================== KONFİGÜRASYON ====================
KAYNAK_TIPI = "youtube"
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"
RTSP_URL = "rtsp://kamera.belediye.gov.tr:554/stream"

# ÖNCE BUNU API'DEN ALACAĞIZ!
KAMERA_ID = 1  # Şimdilik 1 yazdık ama veritabanında yoksa patlar!

PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

MODEL_ADI = 'yolov8n.pt'
CIBOZUNURLUK = (426, 240)
FPS = 10
# ========================================================

class BelediyeKameraTakip:
    def __init__(self):
        self.db = DatabaseManager(PG_CONFIG)
        self.db.connect()
        
        # ÖNCE KAMERA VAR MI KONTROL ET!
        self.kamera_id = self.kamera_kontrol()
        if not self.kamera_id:
            print("❌ Geçerli bir kamera ID'si yok. Önce API'den kamera ekleyin!")
            sys.exit(1)
        
        print("🔄 YOLO modeli yükleniyor...")
        self.model = YOLO(MODEL_ADI)
        print("✅ Model yüklendi!")
        
        self.process = None
        self.running = True
        
        # Sayaçlar - DÜZELTİLDİ!
        self.dakika_baslangic = time.time()
        self.dakika_sayaci = 0
        self.dakikalik_toplam = 0  # Bu sadece dakikalık toplam için
        self.kisi_listesi = deque(maxlen=FPS * 60)
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def kamera_kontrol(self):
        """Kamera ID'sinin veritabanında olup olmadığını kontrol et"""
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM kameralar WHERE id = %s", (KAMERA_ID,))
                sonuc = cur.fetchone()
            self.db.return_connection(conn)
            
            if sonuc:
                print(f"✅ Kamera ID {KAMERA_ID} veritabanında bulundu")
                return KAMERA_ID
            else:
                print(f"❌ Kamera ID {KAMERA_ID} veritabanında YOK!")
                print("   Lütfen önce API'den /youtube-ekle ile bir kamera ekleyin")
                return None
        except Exception as e:
            print(f"⚠️ Kamera kontrol hatası: {e}")
            return None
    
    def signal_handler(self, sig, frame):
        print("\n👋 Program durduruluyor...")
        self.running = False
    
    def get_youtube_stream(self):
        print("📡 YouTube canlı yayınına bağlanılıyor...")
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(YOUTUBE_URL, download=False)
            return info['url'], info.get('title', 'Bilinmiyor')
    
    def start_stream(self):
        if KAYNAK_TIPI == "youtube":
            video_url, baslik = self.get_youtube_stream()
            print(f"✅ {baslik}")
            
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', video_url,
                '-f', 'image2pipe',
                '-pix_fmt', 'bgr24',
                '-vcodec', 'rawvideo',
                '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}",
                '-r', str(FPS),
                '-'
            ]
        else:
            print(f"📡 RTSP kameraya bağlanılıyor: {RTSP_URL}")
            ffmpeg_cmd = [
                'ffmpeg',
                '-rtsp_transport', 'tcp',
                '-i', RTSP_URL,
                '-f', 'image2pipe',
                '-pix_fmt', 'bgr24',
                '-vcodec', 'rawvideo',
                '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}",
                '-r', str(FPS),
                '-'
            ]
        
        self.process = subprocess.Popen(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.DEVNULL, 
            bufsize=10**8
        )
        
        print(f"🎥 Canlı takip başladı! ({KAYNAK_TIPI})")
        print("=" * 60)
    
    def process_frame(self, frame):
        results = self.model(frame, verbose=False)
        
        # Anlık kişi sayısı (BU DOĞRU!)
        anlik_kisi = 0
        for box in results[0].boxes:
            if int(box.cls[0]) == 0:
                anlik_kisi += 1
        
        # Listeye ekle (geçmiş için)
        self.kisi_listesi.append(anlik_kisi)
        
        # Dakikalık toplama EKLE (doğru olan bu!)
        self.dakikalik_toplam += anlik_kisi
        self.dakika_sayaci += 1
        
        # Anlık veriyi kaydet (her 10 saniyede bir)
        if self.dakika_sayaci % (FPS * 10) == 0:
            self.db.anlik_kaydet(self.kamera_id, anlik_kisi)
        
        # Dakika doldu mu?
        if time.time() - self.dakika_baslangic >= 60:
            self.save_minute_data()
        
        # Görüntüyü hazırla (DÜZELTİLDİ!)
        annotated = results[0].plot()
        kalan_sure = 60 - int(time.time() - self.dakika_baslangic)
        
        # ŞİMDİ DOĞRU: anlik_kisi = o andaki kişi sayısı
        # dakikalik_toplam = o dakika boyunca GÖRÜLEN TOPLAM KİŞİ (bir kişi birden çok sayılabilir)
        cv2.putText(annotated, 
                   f"Anlik: {anlik_kisi} | Bu dakika toplam: {self.dakikalik_toplam} | Kalan: {kalan_sure}s", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        return annotated
    
    def save_minute_data(self):
        bitis = datetime.now()
        baslangic = datetime.fromtimestamp(self.dakika_baslangic)
        
        ortalama = self.dakikalik_toplam / self.dakika_sayaci if self.dakika_sayaci > 0 else 0
        maksimum = max(self.kisi_listesi) if self.kisi_listesi else 0
        minimum = min(self.kisi_listesi) if self.kisi_listesi else 0
        
        detaylar = {
            'kaynak_tipi': KAYNAK_TIPI,
            'url': YOUTUBE_URL if KAYNAK_TIPI == 'youtube' else RTSP_URL,
            'cozunurluk': CIBOZUNURLUK,
            'fps': FPS
        }
        
        self.db.dakikalik_kaydet(
            self.kamera_id, baslangic, bitis,
            self.dakikalik_toplam, ortalama,
            maksimum, minimum,
            self.dakika_sayaci / 60.0,
            detaylar
        )
        
        print(f"📊 [{baslangic.strftime('%H:%M:%S')}] "
              f"Dakikalık toplam gorulen: {self.dakikalik_toplam} | "
              f"Ort: {ortalama:.1f} | Maks: {maksimum}")
        
        # Sayaçları sıfırla
        self.dakika_baslangic = time.time()
        self.dakikalik_toplam = 0
        self.dakika_sayaci = 0
        self.kisi_listesi.clear()
    
    def run(self):
        self.start_stream()
        
        width, height = CIBOZUNURLUK
        frame_size = width * height * 3
        
        cv2.namedWindow('Belediye Kamera Takip', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Belediye Kamera Takip', width*2, height*2)
        
        try:
            while self.running:
                raw_frame = self.process.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    print("⚠️ Akış kesildi, yeniden bağlanılıyor...")
                    self.process.terminate()
                    time.sleep(2)
                    self.start_stream()
                    continue
                
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
                display_frame = self.process_frame(frame)
                
                cv2.imshow('Belediye Kamera Takip', display_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                    
        except KeyboardInterrupt:
            print("\n👋 Kullanıcı tarafından durduruldu.")
        finally:
            self.cleanup()
    
    def cleanup(self):
        if self.process:
            self.process.terminate()
        cv2.destroyAllWindows()
        self.db.close()
        print("✅ Program sonlandırıldı.")

if __name__ == "__main__":
    takip = BelediyeKameraTakip()
    takip.run()