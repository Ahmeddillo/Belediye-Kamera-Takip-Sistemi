# opt_yonlu_Idli_kisisayma.py
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
import yaml  # Standart yaml kütüphanesini kullanıyoruz
from database import DatabaseManager

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ==================== AKILLI TRACKER YAPILANDIRICI (GÜNCELLENDİ) ====================
TRACKER_AYAR_DOSYASI = "bytetrack_custom.yaml"

def prepare_tracker():
    try:
        # Ultralytics içindeki orijinal dosyayı bulmaya çalış
        import ultralytics
        ultralytics_path = os.path.dirname(ultralytics.__file__)
        base_config_path = os.path.join(ultralytics_path, "cfg", "trackers", "bytetrack.yaml")
        
        # Eğer dosya yolu yukarıdaki gibi değilse (eski versiyonlar için)
        if not os.path.exists(base_config_path):
             base_config_path = os.path.join(ultralytics_path, "utils", "trackers", "bytetrack.yaml")

        if os.path.exists(base_config_path):
            with open(base_config_path, 'r') as f:
                config = yaml.safe_load(f)
        else:
            # Dosya hiçbir yerde bulunamazsa güvenli bir varsayılan oluştur
            config = {
                "tracker_type": "bytetrack",
                "track_high_thresh": 0.5,
                "track_low_thresh": 0.1,
                "new_track_thresh": 0.6,
                "track_buffer": 30,
                "match_thresh": 0.8,
                "fuse_score": True # Hata veren kritik parametre
            }

        # Hocanın istediği kritik iyileştirmeleri üzerine yaz
        config['track_high_thresh'] = 0.25
        config['track_low_thresh'] = 0.05
        config['new_track_thresh'] = 0.25
        config['track_buffer'] = 60
        config['match_thresh'] = 0.85
        
        with open(TRACKER_AYAR_DOSYASI, 'w') as f:
            yaml.dump(config, f)
        print("✅ Tracker ayarları başarıyla yapılandırıldı.")
    except Exception as e:
        print(f"⚠️ Yapılandırma hatası: {e}. Standart takipçi kullanılacak.")
        return "bytetrack.yaml"
    return TRACKER_AYAR_DOSYASI

# Yapılandırmayı çalıştır
TRACKER_AYAR_DOSYASI = prepare_tracker()
# ========================================================================

# ==================== KONFİGÜRASYON ====================
KAYNAK_TIPI = "hls"
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"
RTSP_URL = "rtsp://kamera.belediye.gov.tr:554/stream"
HLS_URL = "https://content.tvkur.com/l/c77ia4vbb2nj4i0fr85g/master.m3u8"

KAMERA_ID = 2

PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

MODEL_ADI = 'yolov8s.pt' 
CIBOZUNURLUK = (640, 360) 
EKRAN_BOYUTU = (852, 480)
FPS = 10
# ========================================================

class BelediyeKameraTakip:
    def __init__(self):
        self.db = DatabaseManager(PG_CONFIG)
        self.db.connect()
        
        self.color_map = {}
        self.kamera_id = self.kamera_kontrol()
        
        if not self.kamera_id:
            print("❌ Kamera ID hatası! Önce API'den kamera ekleyin.")
            sys.exit(1)
        
        print(f"🔄 YOLO modeli ({MODEL_ADI}) yükleniyor...")
        self.model = YOLO(MODEL_ADI)
        print("✅ Model yüklendi!")
        
        self.process = None
        self.running = True
        
        self.dakika_baslangic = time.time()
        self.son_anlik_kayit_zamani = time.time()
        
        self.dakika_sayaci = 0
        self.dakikalik_toplam_gorulme = 0
        self.dk_kisiler = {}  
        self.kisi_listesi = deque(maxlen=FPS * 60)
        
        signal.signal(signal.SIGINT, self.signal_handler)
        print("✅ Sistem başlatıldı, video bekleniyor...")

    def get_color(self, track_id):
        if track_id not in self.color_map:
            if len(self.color_map) > 10000:
                self.color_map.clear()
            rng = np.random.default_rng(int(track_id))
            self.color_map[track_id] = tuple(rng.integers(0, 255, 3).tolist())
        return self.color_map[track_id]

    def kamera_kontrol(self):
        try:
            conn = self.db.get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM kameralar WHERE id = %s", (KAMERA_ID,))
                sonuc = cur.fetchone()
            self.db.return_connection(conn)
            return KAMERA_ID if sonuc else None
        except Exception as e:
            print(f"❌ DB bağlantı hatası: {e}")
            return None

    def signal_handler(self, sig, frame):
        print("\n👋 Program durduruluyor...")
        self.running = False

    def get_youtube_stream(self):
        print("📡 YouTube'a bağlanılıyor...")
        ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(YOUTUBE_URL, download=False)
            return info['url']

    def start_stream(self):
        if self.process is not None:
            self.process.terminate()
            self.process = None

        video_url = ""
        if KAYNAK_TIPI == "youtube":
            video_url = self.get_youtube_stream()
            print("✅ YouTube bağlantısı kuruldu")
        elif KAYNAK_TIPI == "hls":
            video_url = HLS_URL
            print("✅ HLS bağlantısı kuruldu")
        else:
            video_url = RTSP_URL
            print(f"📡 RTSP: {RTSP_URL}")

        ffmpeg_cmd = [
            'ffmpeg',
            '-headers', 'Referer: https://player.tvkur.com/\r\nx-referer: https://player.tvkur.com/\r\n',
            '-i', video_url,
            '-f', 'image2pipe', '-pix_fmt', 'bgr24', 
            '-vcodec', 'rawvideo', '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}", 
            '-r', str(FPS), '-'
        ]
        
        if KAYNAK_TIPI != "hls":
            del ffmpeg_cmd[1:3]

        self.process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def process_frame(self, frame):
        h, w = frame.shape[:2]
        cizgi_y = int(h * 0.6)
        
        results = self.model.track(frame, persist=True, tracker=TRACKER_AYAR_DOSYASI, verbose=False, classes=[0])
        
        annotated = cv2.resize(frame, EKRAN_BOYUTU)
        scale_x = EKRAN_BOYUTU[0] / CIBOZUNURLUK[0]
        scale_y = EKRAN_BOYUTU[1] / CIBOZUNURLUK[1]
        
        ekran_cizgi_y = int(cizgi_y * scale_y)
        cv2.line(annotated, (0, ekran_cizgi_y), (EKRAN_BOYUTU[0], ekran_cizgi_y), (0, 0, 255), 3)

        current_ids_in_frame = set()
        anlik_kisi = 0

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box)
                ayak_ucu = y2
                
                if ayak_ucu > cizgi_y:
                    anlik_kisi += 1
                    current_ids_in_frame.add(track_id)

                    sx1, sy1 = int(x1*scale_x), int(y1*scale_y)
                    sx2, sy2 = int(x2*scale_x), int(y2*scale_y)
                    
                    color = self.get_color(track_id)
                    cv2.rectangle(annotated, (sx1, sy1), (sx2, sy2), color, 2)
                    cv2.putText(annotated, f"ID:{track_id}", (sx1, sy1-5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        for id_ in current_ids_in_frame:
            if id_ not in self.dk_kisiler:
                self.dk_kisiler[id_] = datetime.now()
        
        self.dakikalik_toplam_gorulme += anlik_kisi
        self.dakika_sayaci += 1
        
        simdi = time.time()
        if simdi - self.son_anlik_kayit_zamani >= 10:
            self.db.anlik_kaydet(self.kamera_id, anlik_kisi)
            self.son_anlik_kayit_zamani = simdi
        
        if time.time() - self.dakika_baslangic >= 60:
            self.save_minute_data()
        
        cv2.rectangle(annotated, (0,0), (600, 80), (0,0,0), -1)
        cv2.putText(annotated, f"ANLIK (Cizgi Alti): {anlik_kisi}", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(annotated, f"DAKIKALIK FARKLI KISI: {len(self.dk_kisiler)}", 
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        
        return annotated

    def save_minute_data(self):
        bitis = datetime.now()
        baslangic = datetime.fromtimestamp(self.dakika_baslangic)
        farkli_sayi = len(self.dk_kisiler)
        kisi_listesi = sorted([int(x) for x in list(self.dk_kisiler.keys())])
        ortalama = self.dakikalik_toplam_gorulme / self.dakika_sayaci if self.dakika_sayaci > 0 else 0
        
        detaylar = {
            'kaynak_tipi': KAYNAK_TIPI,
            'farkli_kisi_sayisi': farkli_sayi,
            'kisi_id_listesi': kisi_listesi,
            'cozunurluk': CIBOZUNURLUK
        }
        
        self.db.dakikalik_kaydet(
            self.kamera_id, baslangic, bitis,
            self.dakikalik_toplam_gorulme, ortalama, farkli_sayi, 0,
            self.dakika_sayaci / 60.0, detaylar
        )
        
        print(f"\n{'='*60}")
        print(f"📊 DAKİKA RAPORU [{baslangic.strftime('%H:%M:%S')}]")
        print(f"✅ FARKLI KİŞİ SAYISI: {farkli_sayi}")
        print(f"👀 Toplam Görülme (Frame bazlı): {self.dakikalik_toplam_gorulme}")
        print(f"{'='*60}\n")
        
        self.dakika_baslangic = time.time()
        self.dakikalik_toplam_gorulme = 0
        self.dakika_sayaci = 0
        self.dk_kisiler.clear()
        self.kisi_listesi.clear()

    def run(self):
        self.start_stream()
        frame_size = CIBOZUNURLUK[0] * CIBOZUNURLUK[1] * 3
        
        print("\n🎥 CANLI TAKİP BAŞLADI (ByteTrack Aktif)")
        
        try:
            while self.running:
                raw_frame = self.process.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    print("🔄 Akış kesildi/bitti, yeniden bağlanılıyor...")
                    self.start_stream()
                    continue
                
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((CIBOZUNURLUK[1], CIBOZUNURLUK[0], 3))
                display_frame = self.process_frame(frame)
                cv2.imshow('Belediye Kamera Takip', display_frame)
                
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except KeyboardInterrupt:
            print("\n👋 Durduruluyor (KeyboardInterrupt)...")
        finally:
            self.cleanup()

    def cleanup(self):
        if self.process: 
            self.process.terminate()
        cv2.destroyAllWindows()
        self.db.close()
        print("\n✅ Program sonlandırıldı.")

if __name__ == "__main__":
    takip = BelediyeKameraTakip()
    takip.run()