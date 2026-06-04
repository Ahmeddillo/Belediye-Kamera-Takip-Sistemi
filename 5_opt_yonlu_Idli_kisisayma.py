# 5_opt_yonlu_Idli_kisisayma.py
import cv2
import subprocess
import numpy as np
from ultralytics import YOLO
import time
from datetime import datetime
import yt_dlp
import os
import signal
import sys
import yaml
from database import DatabaseManager

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Konfigürasyon:
# 1.1) Burada olabilecek tüm kaynakları, kamera ID'si ve veritabanı ayarları setlendi
KAYNAK_TIPI = "youtube"
YOUTUBE_URL = "https://www.youtube.com/watch?v=DjdUEyjx8GM"
RTSP_URL = "rtsp://kamera.belediye.gov.tr:554/stream"
HLS_URL = "https://content.tvkur.com/l/c77ia4vbb2nj4i0fr85g/master.m3u8"

KAMERA_ID = 1

PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

# 1.2) Ondan sonra da model adı, ekran boyutu ve çözünürlük değerleri belirlendi

MODEL_ADI = 'yolov8s.pt' 
CIBOZUNURLUK = (640, 360) 
EKRAN_BOYUTU = (852, 480)
FPS = 10
TRACKER_AYAR_DOSYASI = "bytetrack_custom.yaml" # Önemli: bu dosya bytetrack algoritmasının hassas ayarlarnı içerir
# ========================================================

# 2) tracker ayarlarını sisteme uygun hale getirme
def prepare_tracker():
    """Tracker ayarlarını sistemle uyumlu ve hocanın istediği şekilde hazırlar."""
    try:
        
        # 2.1) Alttaki kütüphanenin cihazdaki yeri bulunmaya çalışılır
        import ultralytics
        ultralytics_path = os.path.dirname(ultralytics.__file__)
        # 2.2) alttaki uzantılara sahip olan dosyaları ara
        base_config_path = os.path.join(ultralytics_path, "cfg", "trackers", "bytetrack.yaml")
        
        if not os.path.exists(base_config_path):
             base_config_path = os.path.join(ultralytics_path, "utils", "trackers", "bytetrack.yaml")
        
        # 2.3) bulunmadıysa varsayılan değerler taban olarak alınır
        if os.path.exists(base_config_path):
            with open(base_config_path, 'r') as f:
                config = yaml.safe_load(f)
        # 2.4) Dosya hiç bulunmazsa ayarlar setlenir
        else:
            config = {
                "tracker_type": "bytetrack",
                "track_high_thresh": 0.5, "track_low_thresh": 0.1,
                "new_track_thresh": 0.6, "track_buffer": 30,
                "match_thresh": 0.8, "fuse_score": True 
            }

        # 2.4) takibin toleranslı sayılması için değer güncellemeler alttaki gibi olur
        config.update({
            'track_high_thresh': 0.25,
            'track_low_thresh': 0.05,
            'new_track_thresh': 0.25,
            'track_buffer': 60,
            'match_thresh': 0.85
        })
        
        # 2.5) güncellemeleri yaml dosyasına yaz ve hata oluşrsa hatayı döndür, en sonda da yaml dosyasını dödür
        with open(TRACKER_AYAR_DOSYASI, 'w') as f:
            yaml.dump(config, f)
        print("✅ Tracker ayarları başarıyla yapılandırıldı.")
        
    except Exception as e:
        print(f"⚠️ Yapılandırma hatası: {e}. Standart takipçi kullanılacak.")
        return "bytetrack.yaml"
    return TRACKER_AYAR_DOSYASI

# 3) Takip sürecinin ana merkezi olan fonksiyon, aşağıdadır:
class BelediyeKameraTakip:
    def __init__(self, tracker_path):
        # 3.1) postgresql bağlantısı kurulur, 
        self.db = DatabaseManager(PG_CONFIG)
        self.db.connect()
        
        # 3.2) obje başına renk ayarları, kamera ID kimlik doğrulaması yapılır.
        self.tracker_path = tracker_path
        self.color_map = {}
        self.kamera_id = self.kamera_kontrol()
        
        # eğer kamera ID'si sistemde yoksa, gücenli bir şekilde kapatır
        if not self.kamera_id:
            print("❌ Kamera ID hatası! Önce API'den kamera ekleyin.")
            sys.exit(1)
        
        # 3.3) model belleğe yüklenir
        print(f"🔄 YOLO modeli ({MODEL_ADI}) yükleniyor...")
        self.model = YOLO(MODEL_ADI) # burda model adı değeri: yolo8s.pt
        print("✅ Model yüklendi!")
        
        self.process = None
        self.running = True # sistemin çalışmaya devam edip etmeyeceğini düşünür
        
        # 3.4) anlık veri ve 1 dklık veri için sayaçlar oluşturulur
        self.dakika_baslangic = time.time()
        self.son_anlik_kayit_zamani = time.time()
        
        # 3.5) kaçıncı dk'da olduğumuzu, dk'lık tespit edilen kişiler için bir listeyi oluşturup, kişileri ona kaydetmek için hazırlaırız
        self.dakika_sayaci = 0
        self.dakikalik_toplam_gorulme = 0
        self.dk_kisiler = {}  

        signal.signal(signal.SIGINT, self.signal_handler)
        print("✅ Sistem başlatıldı, video bekleniyor...")

    # 4) takip edilen her nesneye benzersiz bir renk atanır
    def get_color(self, track_id):
        if track_id not in self.color_map:
            if len(self.color_map) > 10000:
                self.color_map.clear()
            rng = np.random.default_rng(int(track_id))
            self.color_map[track_id] = tuple(rng.integers(0, 255, 3).tolist())
        return self.color_map[track_id]

    # 5) kullanılan kamera'yı tanımak, yani kimlik doğrulaması için bir fonksiyon hazırlanır
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

    # 6) sinyal akışı için bir fonksiyon hazırlanır
    def signal_handler(self, sig, frame):
        print("\n👋 Program durduruluyor...")
        self.running = False

    # 7) youtube canlı yayın bağlantısı için bir fonksiyon hazırlanır
    def get_youtube_stream(self):
        print("📡 YouTube'a bağlanılıyor...")
        ydl_opts = {'format': 'best[ext=mp4]/best', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(YOUTUBE_URL, download=False)
            return info['url']

    # 8) farklı kaynaklardan gelen video kaynaklarını, FFmepg'ye dönüştürme işleminden sorumlu, YOLO formatına uygun olsun diye
    def start_stream(self):
        if self.process is not None:
            self.process.terminate()
            self.process = None

        video_url = ""
        if KAYNAK_TIPI == "youtube":
            video_url = self.get_youtube_stream()
        elif KAYNAK_TIPI == "hls":
            video_url = HLS_URL
        else:
            video_url = RTSP_URL

        # HOCANIN DÜZELTMESİ: Dinamik FFmpeg komutu oluşturma
        ffmpeg_cmd = ['ffmpeg']
        if KAYNAK_TIPI == "hls":
            ffmpeg_cmd += ['-headers', 'Referer: https://player.tvkur.com/\r\nx-referer: https://player.tvkur.com/\r\n']
            
        ffmpeg_cmd += [
            '-i', video_url,
            '-f', 'image2pipe', '-pix_fmt', 'bgr24', 
            '-vcodec', 'rawvideo', '-s', f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}", 
            '-r', str(FPS), '-'
        ]
        self.process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # 9) görüntü karesini işlemek içim vardır 
    def process_frame(self, frame):
        h, w = frame.shape[:2]
        cizgi_y = int(h * 0.6) # görüntünün yüzde 60'nın çizgisi çizilir
        
        results = self.model.track(frame, persist=True, tracker=self.tracker_path, verbose=False, classes=[0])
        
        annotated = cv2.resize(frame, EKRAN_BOYUTU)
        scale_x = EKRAN_BOYUTU[0] / CIBOZUNURLUK[0] # yatay ölçek 
        scale_y = EKRAN_BOYUTU[1] / CIBOZUNURLUK[1] # dikey ölçek 
        
        ekran_cizgi_y = int(cizgi_y * scale_y)
        cv2.line(annotated, (0, ekran_cizgi_y), (EKRAN_BOYUTU[0], ekran_cizgi_y), (0, 0, 255), 3)

        current_ids_in_frame = set() # ilk değişken değerleri atanır
        anlik_kisi = 0

        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.int().cpu().numpy()

            for box, track_id in zip(boxes, track_ids):
                x1, y1, x2, y2 = map(int, box) # tespit edilen kutu koordinatları
                if y2 > cizgi_y: # eğer kişi çizginin altındaysa
                    anlik_kisi += 1 # kişi ayılır ve anlık kişi sayısı bir arttırılı
                    current_ids_in_frame.add(track_id) # kimliği de ayrıca kaydedilir
                    sx1, sy1 = int(x1*scale_x), int(y1*scale_y)
                    sx2, sy2 = int(x2*scale_x), int(y2*scale_y)
                    color = self.get_color(track_id)
                    cv2.rectangle(annotated, (sx1, sy1), (sx2, sy2), color, 2) # burda da kutu çizme
                    cv2.putText(annotated, f"ID:{track_id}", (sx1, sy1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2) # ve ID atama kısmı vardır

        for id_ in current_ids_in_frame:
            if id_ not in self.dk_kisiler:
                self.dk_kisiler[id_] = datetime.now()
        
        # dakikalık işlemler...
        self.dakikalik_toplam_gorulme += anlik_kisi
        self.dakika_sayaci += 1
        
        # CANLI AKIŞ İÇİN İYİLEŞTİRME: 10 sn yerine 2 sn'de bir DB'ye yaz
        simdi = time.time()
        if simdi - self.son_anlik_kayit_zamani >= 2:
            self.db.anlik_kaydet(self.kamera_id, anlik_kisi)
            self.son_anlik_kayit_zamani = simdi
        
        if time.time() - self.dakika_baslangic >= 60:
            self.save_minute_data()
        
        cv2.rectangle(annotated, (0,0), (600, 80), (0,0,0), -1)
        cv2.putText(annotated, f"ANLIK: {anlik_kisi} | FARKLI: {len(self.dk_kisiler)}", 
                    (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        return annotated

    # 10) zaman aralıklı kaydetme kısmı 
    def save_minute_data(self):
        # 10.1) zaman aralığı hesaplanır
        bitis = datetime.now()
        baslangic = datetime.fromtimestamp(self.dakika_baslangic)
        farkli_sayi = len(self.dk_kisiler)
        ortalama = self.dakikalik_toplam_gorulme / self.dakika_sayaci if self.dakika_sayaci > 0 else 0
        
        # 10.2) json verileri teknik olarak hazırlanır
        detaylar = {
            'kaynak_tipi': KAYNAK_TIPI, 
            'farkli_kisi_sayisi': farkli_sayi, 
            'kisi_id_listesi': sorted([int(x) for x in self.dk_kisiler.keys()])
        }
        
        # 10.3) veri tabanında dakikalık veriler kaydedilir ve terminal'de belirtilir
        self.db.dakikalik_kaydet(self.kamera_id, baslangic, bitis, self.dakikalik_toplam_gorulme, 
                                 ortalama, farkli_sayi, 0, self.dakika_sayaci / 60.0, detaylar)
        
        print(f"📊 DAKİKA RAPORU [{baslangic.strftime('%H:%M:%S')}] -> Farklı: {farkli_sayi}")
        self.dakika_baslangic, self.dakikalik_toplam_gorulme, self.dakika_sayaci = time.time(), 0, 0
        self.dk_kisiler.clear()

    def run(self):
        self.start_stream()
        frame_size = CIBOZUNURLUK[0] * CIBOZUNURLUK[1] * 3
        try:
            while self.running:
                raw_frame = self.process.stdout.read(frame_size)
                if len(raw_frame) != frame_size:
                    self.start_stream()
                    continue
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((CIBOZUNURLUK[1], CIBOZUNURLUK[0], 3))
                cv2.imshow('Kamera Takip', self.process_frame(frame))
                if cv2.waitKey(1) & 0xFF == ord('q'): break
        except KeyboardInterrupt: pass
        finally: self.cleanup()

    def cleanup(self):
        if self.process: self.process.terminate()
        cv2.destroyAllWindows()
        self.db.close()
        print("✅ Program sonlandırıldı.")

# HOCANIN DÜZELTMESİ: Global scope yerine main bloğu kullanımı
if __name__ == "__main__":
    current_tracker = prepare_tracker()
    takip = BelediyeKameraTakip(tracker_path=current_tracker)
    takip.run()
