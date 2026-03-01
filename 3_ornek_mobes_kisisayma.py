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
KAYNAK_TIPI = "hls"
HLS_URL = "https://content.tvkur.com/l/c77ia4vbb2nj4i0fr85g/master.m3u8"

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
        self.son_sayilar = deque(maxlen=5)  # Hareketli ortalama için
        
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

    def start_stream(self):
        if KAYNAK_TIPI == "hls":
            ffmpeg_cmd = [
                'ffmpeg',
                '-headers', 'Referer: https://player.tvkur.com/\r\nx-referer: https://player.tvkur.com/\r\n',
                '-i', HLS_URL,
                '-f', 'image2pipe',
                '-pix_fmt', 'bgr24',
                '-vcodec', 'rawvideo',
                '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}",
                '-r', str(FPS),
                '-'
            ]
        else:
            print("❌ Geçersiz kaynak tipi!")
            sys.exit(1)
            
        self.process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

    def process_frame(self, frame):
        h, w = frame.shape[:2]
        cizgi_y = int(h * 0.6)
        
        # Modeli çalıştır
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
            if int(box.cls[0]) == 0:
                coords = box.xyxy[0].tolist()
                ayak_ucu = coords[3]
                
                if ayak_ucu > cizgi_y:
                    anlik_kisi += 1
                    
                    x1, y1, x2, y2 = int(coords[0]*scale_x), int(coords[1]*scale_y), \
                                     int(coords[2]*scale_x), int(coords[3]*scale_y)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    ayak_x = int(coords[0] * scale_x + (coords[2]-coords[0])*scale_x/2)
                    ayak_y = int(ayak_ucu * scale_y)
                    cv2.circle(annotated, (ayak_x, ayak_y), 5, (255, 0, 0), -1)

        # Hareketli ortalama ile kararlı sayı
        self.son_sayilar.append(anlik_kisi)
        kararli_sayi = int(sum(self.son_sayilar) / len(self.son_sayilar))

        self.kisi_listesi.append(anlik_kisi)
        self.dakikalik_toplam += anlik_kisi
        self.dakika_sayaci += 1
        
        if self.dakika_sayaci % (FPS * 10) == 0:
            self.db.anlik_kaydet(self.kamera_id, anlik_kisi)
        
        if time.time() - self.dakika_baslangic >= 60:
            self.save_minute_data()
        
        # Bilgi paneli
        cv2.rectangle(annotated, (0,0), (550, 90), (0,0,0), -1)
        cv2.putText(annotated, f"Kisi: {kararli_sayi} (anlik: {anlik_kisi})", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annotated, f"Bu dakika: {self.dakikalik_toplam}", 
                    (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(annotated, f"Cizgi Altindakiler Sayilir | FPS: {FPS}", 
                    (10, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
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
            {'res': EKRAN_BOYUTU, 'cizgi_orani': 0.6, 'kaynak': 'hls'}
        )
        
        
        # KONSOLA YAZDIR (EKLEDİK!)
        print(f"📊 [{baslangic.strftime('%H:%M:%S')}] "
          f"Dakikalık toplam gorulen: {self.dakikalik_toplam} | "
          f"Ort: {ortalama:.1f} | Maks: {maks}")
        
        self.dakika_baslangic = time.time()
        self.dakikalik_toplam = 0
        self.dakika_sayaci = 0
        self.kisi_listesi.clear()

    def run(self):
        self.start_stream()
        frame_size = CIBOZUNURLUK[0] * CIBOZUNURLUK[1] * 3
        cv2.namedWindow('Belediye Kamera Takip - Sayim Bolgesi', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Belediye Kamera Takip - Sayim Bolgesi', EKRAN_BOYUTU[0], EKRAN_BOYUTU[1])
        
        print("Canlı yayında kişi sayımı başladı (HLS)...")
        print("Çıkmak için 'q' tuşuna basın")
        
        try:
            while self.running:
                raw_frame = self.process.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    print("🔄 Akış kesildi, yeniden bağlanıyor...")
                    self.process.terminate()
                    time.sleep(1)
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