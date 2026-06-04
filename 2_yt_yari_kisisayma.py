# 2_yt_yari_kisisayma.py
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

# Konfigürasyon:
KAYNAK_TIPI = "youtube" #youtube değil de rstp kullanacaksan, bu değeri rstp olarak değiştirmen lazım.
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"
RTSP_URL = "rtsp://kamera.belediye.gov.tr:554/stream"

KAMERA_ID = 1 

PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

MODEL_ADI = 'yolov8n.pt'
CIBOZUNURLUK = (426, 240) # İşleme çözünürlüğü (Hız için düşük tutuyoruz)
EKRAN_BOYUTU = (852, 480) # Görüntüleme çözünürlüğü (2 kat büyük)
FPS = 10
# ========================================================

class BelediyeKameraTakip:
    def __init__(self):
        self.db = DatabaseManager(PG_CONFIG)
        self.db.connect()
        
        self.kamera_id = self.kamera_kontrol()
        if not self.kamera_id:
            print("❌ Kamera ID hatası!")
            sys.exit(1)
        
        self.model = YOLO(MODEL_ADI)
        self.process = None
        self.running = True
        
        self.dakika_baslangic = time.time()
        self.dakika_sayaci = 0
        self.dakikalik_toplam = 0
        self.kisi_listesi = deque(maxlen=FPS * 60)
        
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def kamera_kontrol(self):
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM kameralar WHERE id = %s", (KAMERA_ID,))
                sonuc = cur.fetchone()
            self.db.return_connection(conn)
            return KAMERA_ID if sonuc else None
        except: return None

    def signal_handler(self, sig, frame):
        self.running = False

    def get_youtube_stream(self):
        ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(YOUTUBE_URL, download=False)
            return info['url']

    def start_stream(self):
        video_url = self.get_youtube_stream() if KAYNAK_TIPI == "youtube" else RTSP_URL
        ffmpeg_cmd = [
            'ffmpeg', '-i', video_url, '-f', 'image2pipe', '-pix_fmt', 'bgr24', 
            '-vcodec', 'rawvideo', '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}", 
            '-r', str(FPS), '-'
        ]
        self.process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def process_frame(self, frame):
        h, w = frame.shape[:2]
        # Çizgi yüksekliğini sabitleyelim: Örneğin 240 piksel yüksekliğin %60'ı
        # cizgi_y = h // 2  # Eski yarıda çizgi
        cizgi_y = int(h * 0.6)  # Yeni: yüksekliğin %60'ı (daha gerçekçi)
        
        # Modeli çalıştır (orijinal küçük frame'de)
        results = self.model(frame, verbose=False)
        
        # Görüntüyü büyük ekrana hazırla
        annotated = cv2.resize(frame, EKRAN_BOYUTU)
        scale_x = EKRAN_BOYUTU[0] / CIBOZUNURLUK[0]
        scale_y = EKRAN_BOYUTU[1] / CIBOZUNURLUK[1]
        
        # Çizgiyi büyük ekrana göre ölçekle ve çiz
        ekran_cizgi_y = int(cizgi_y * scale_y)
        cv2.line(annotated, (0, ekran_cizgi_y), (EKRAN_BOYUTU[0], ekran_cizgi_y), (0, 0, 255), 3)
        cv2.putText(annotated, "SAYIM BOLGESI", (10, ekran_cizgi_y + 25), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        anlik_kisi = 0
        for box in results[0].boxes:
            if int(box.cls[0]) == 0:  # İnsan
                coords = box.xyxy[0].tolist()
                # İnsanın ayak ucu (alt koordinat)
                ayak_ucu = coords[3]
                # Göbek hizası (orta nokta) - daha hassas
                govde_ortasi = (coords[1] + coords[3]) / 2
                
                # KURAL: İnsanın alt kısmı çizgiyi geçtiyse say
                # Alternatif: Gövde ortası çizgiyi geçtiyse say (daha hassas)
                if ayak_ucu > cizgi_y:
                    anlik_kisi += 1
                    
                    # Kutuyu büyük ekrana ölçekle ve yeşil çiz
                    x1, y1, x2, y2 = int(coords[0]*scale_x), int(coords[1]*scale_y), \
                                     int(coords[2]*scale_x), int(coords[3]*scale_y)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # İnsanın ayak ucuna küçük bir işaret koy
                    ayak_x = int(coords[0] * scale_x + (coords[2]-coords[0])*scale_x/2)
                    ayak_y = int(ayak_ucu * scale_y)
                    cv2.circle(annotated, (ayak_x, ayak_y), 5, (255, 0, 0), -1)

        self.kisi_listesi.append(anlik_kisi)
        self.dakikalik_toplam += anlik_kisi
        self.dakika_sayaci += 1
        
        if self.dakika_sayaci % (FPS * 10) == 0:
            self.db.anlik_kaydet(self.kamera_id, anlik_kisi)
        
        if time.time() - self.dakika_baslangic >= 60:
            self.save_minute_data()
        
        # Bilgi paneli
        cv2.rectangle(annotated, (0,0), (500, 70), (0,0,0), -1)
        cv2.putText(annotated, f"Kisi: {anlik_kisi} | Bu dakika: {self.dakikalik_toplam}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(annotated, f"Cizgi Altindakiler Sayilir | FPS: {FPS}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return annotated

    def save_minute_data(self):
        bitis = datetime.now()
        baslangic = datetime.fromtimestamp(self.dakika_baslangic)
        ortalama = self.dakikalik_toplam / self.dakika_sayaci if self.dakika_sayaci > 0 else 0
        maks = max(self.kisi_listesi) if self.kisi_listesi else 0
        mini = min(self.kisi_listesi) if self.kisi_listesi else 0
        
        self.db.dakikalik_kaydet(
            self.kamera_id, baslangic, bitis, 
            self.dakikalik_toplam, ortalama, 
            maks, mini, 
            self.dakika_sayaci/60.0, 
            {'res': EKRAN_BOYUTU, 'cizgi_orani': 0.6}
        )
        
        # KONSOLA YAZDIR (EKLEDİK!)
        print(f"📊 [{baslangic.strftime('%H:%M:%S')}] "
          f"Dakikalık toplam gorulen: {self.dakikalik_toplam} | "
          f"Ort: {ortalama:.1f} | Maks: {maks}")
        
        # Sayaçları sıfırla
        self.dakika_baslangic = time.time()
        self.dakikalik_toplam = 0
        self.dakika_sayaci = 0
        self.kisi_listesi.clear()

    def run(self):
        self.start_stream()
        frame_size = CIBOZUNURLUK[0] * CIBOZUNURLUK[1] * 3
        cv2.namedWindow('Belediye Kamera Takip - Sayim Bolgesi', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Belediye Kamera Takip - Sayim Bolgesi', EKRAN_BOYUTU[0], EKRAN_BOYUTU[1])
        
        try:
            while self.running:
                raw_frame = self.process.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    print("🔄 Akış kesildi, yeniden bağlanıyor...")
                    self.start_stream()
                    continue
                
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((CIBOZUNURLUK[1], CIBOZUNURLUK[0], 3))
                display_frame = self.process_frame(frame)
                cv2.imshow('Belediye Kamera Takip - Sayim Bolgesi', display_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
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
