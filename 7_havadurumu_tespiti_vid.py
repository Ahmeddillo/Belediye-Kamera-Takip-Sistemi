# 7_havadurumu_tespiti_vid.py
import cv2
import subprocess
import numpy as np
import time
import os
import signal
import threading
import queue
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from database import DatabaseManager  

# PyTorch'un tüm CPU'yu sömürmesini engelle
torch.set_num_threads(2)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Konfigürasyon:
KAYNAK_TIPI = "youtube"   # "hls", "rtsp" veya "youtube"

HLS_URL     = "https://seyret.malatya.bel.tr/streams/camera_1773435571403_555.m3u8"
RTSP_URL    = "rtsp://kamera.belediye.gov.tr:554/stream"
YOUTUBE_URL = "https://www.youtube.com/watch?v=wqctLW0Hb_0"

KAMERA_ID = 1  

PG_CONFIG = {  
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

CIBOZUNURLUK = (640, 360)
EKRAN_BOYUTU = (852, 480)
FPS          = 10

HAVA_ANALIZ_ARALIGI = 5   # saniye — CLIP ne sıklıkla çalışsın

ETIKET_SOZLUGU = {
    "clear sunny weather with bright sky":              "Gunesli",
    "partly cloudy sky with some sun":                  "Parcali Bulutlu",
    "overcast cloudy and grey sky":                     "Bulutlu / Kapali",
    "rainy weather with wet ground and puddles":        "Yagmurlu / Islak",
    "snowy winter or thick foggy weather":              "Karli / Sisli",
    "dark night time street view":                      "Gece / Karanlik",
    "blurry vision or dirty camera lens obstruction":   "Kirli Lens",
}
INGILIZCE_ETIKETLER = list(ETIKET_SOZLUGU.keys())
# ========================================================


class HavaDurumuRadari:
    def __init__(self):
        self.db = DatabaseManager(PG_CONFIG)  
        self.db.connect()                     

        print("🔄 CLIP modeli yükleniyor...")
        self.clip_model     = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
        print("✅ CLIP yüklendi!")

        self.process = None
        self.running = True

        self.frame_kuyrugu = queue.Queue(maxsize=2)
        self.analiz_kuyrugu = queue.Queue(maxsize=1)

        self.mevcut_hava_durumu = "Analiz ediliyor..."
        self.son_hava_analiz_zamani = 0

        threading.Thread(target=self._ffmpeg_okuyucu,    daemon=True).start()
        threading.Thread(target=self._clip_isleyicisi,   daemon=True).start()

        signal.signal(signal.SIGINT, self.signal_handler)
        print("✅ Sistem hazır.")

    def _video_url_al(self):
        if KAYNAK_TIPI == "youtube":
            import yt_dlp
            print("📡 YouTube URL çözümleniyor...")
            with yt_dlp.YoutubeDL({"format": "best[ext=mp4]/best", "quiet": True}) as ydl:
                info = ydl.extract_info(YOUTUBE_URL, download=False)
                return info["url"]
        elif KAYNAK_TIPI == "hls":
            return HLS_URL
        else:
            return RTSP_URL

    def _ffmpeg_baslat(self):
        if self.process:
            try:
                self.process.terminate()
            except Exception:
                pass

        video_url = self._video_url_al()
        print(f"📡 Bağlanıyor: {video_url[:60]}...")

        cmd = ["ffmpeg"]

        if KAYNAK_TIPI == "hls":
            cmd += [
                "-headers",
                "Referer: https://seyret.malatya.bel.tr/\r\n"
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "Chrome/120.0.0.0 Safari/537.36\r\n",
            ]

        cmd += [
            "-i", video_url,
            "-f", "image2pipe",
            "-pix_fmt", "bgr24",
            "-vcodec", "rawvideo",
            "-s", f"{CIBOZUNURLUK[0]}x{CIBOZUNURLUK[1]}",
            "-r", str(FPS),
            "-",
        ]

        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _ffmpeg_okuyucu(self):
        # FFmpeg üzerinden gelen ham bayt verilerini okuyup görüntü karelerine (frame) dönüştüren döngü
        frame_size = CIBOZUNURLUK[0] * CIBOZUNURLUK[1] * 3
        self.process = self._ffmpeg_baslat()

        while self.running:
            raw = self.process.stdout.read(frame_size)

            # Akış kesilirse süreci yeniden başlatarak bağlantıyı tazeler
            if len(raw) != frame_size:
                print("🔄 Akış kesildi, yeniden bağlanılıyor...")
                time.sleep(1)
                self.process = self._ffmpeg_baslat()
                continue

            # Ham veriyi numpy dizisine çevirip görüntü formatına sokar
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                (CIBOZUNURLUK[1], CIBOZUNURLUK[0], 3)
            )

            # Kuyruk doluysa en eski kareyi atarak güncel kalmayı sağlar (buffer şişmesini önler)
            if self.frame_kuyrugu.full():
                try:
                    self.frame_kuyrugu.get_nowait()
                except queue.Empty:
                    pass

            self.frame_kuyrugu.put(frame)

    def _clip_isleyicisi(self):
        # Analiz kuyruğuna düşen kareleri yapay zeka (CLIP) ile sınıflandıran iş parçacığı
        while self.running:
            try:
                frame = self.analiz_kuyrugu.get(timeout=1)
            except queue.Empty:
                continue

            # OpenCV formatını (BGR) CLIP modelinin beklediği PIL/RGB formatına dönüştürür
            rgb     = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            goruntu = Image.fromarray(rgb)

            # Görüntüyü ve metin etiketlerini modele hazırlayıp tensöre dönüştürür
            inputs = self.clip_processor(
                text=INGILIZCE_ETIKETLER,
                images=goruntu,
                return_tensors="pt",
                padding=True,
            )

            with torch.no_grad():
                outputs = self.clip_model(**inputs)

            # Model sonuçlarını olasılık değerlerine döküp en yüksek tahminli etiketi seçer
            ihtimaller   = outputs.logits_per_image.softmax(dim=1).cpu().numpy()[0]
            en_iyi_index = ihtimaller.argmax()
            etiket_tr    = ETIKET_SOZLUGU[INGILIZCE_ETIKETLER[en_iyi_index]]
            oran         = ihtimaller[en_iyi_index] * 100

            # Tahmin sonuçlarını arayüzde göstermek üzere günceller ve veritabanına kaydeder
            self.mevcut_hava_durumu = f"{etiket_tr} (%{oran:.1f})"
            print(f"🌡️  {self.mevcut_hava_durumu}")

            self.db.hava_durumu_kaydet(KAMERA_ID, etiket_tr, float(round(oran, 2)))  # ++ EKLENDİ

    def run(self):
        # Görselleştirme ve ana döngü yönetimi
        print("\n🎥 CANLI YAYIN BAŞLADI — çıkmak için 'q'\n")

        while self.running:
            try:
                # Görüntüleme kuyruğundan en son kareyi alır
                frame = self.frame_kuyrugu.get(timeout=0.1)
            except queue.Empty:
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
                continue

            # Belirlenen zaman aralıklarıyla (HAVA_ANALIZ_ARALIGI) analiz kuyruğuna kopya gönderir
            simdi = time.time()
            if (simdi - self.son_hava_analiz_zamani > HAVA_ANALIZ_ARALIGI
                    and not self.analiz_kuyrugu.full()):
                self.analiz_kuyrugu.put(frame.copy())
                self.son_hava_analiz_zamani = simdi

            # Ekran üzerine bilgi paneli ve analiz sonuçlarını yazdırır
            annotated = cv2.resize(frame, EKRAN_BOYUTU)
            cv2.rectangle(annotated, (0, 0), (520, 75), (0, 0, 0), -1)
            cv2.putText(annotated, "CANLI HAVA DURUMU RADARI",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.putText(annotated, f"Durum: {self.mevcut_hava_durumu}",
                        (10, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

            cv2.imshow("Canli Hava Durumu Tespiti", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.cleanup()

    def signal_handler(self, sig, frame):
        # Yazılımın dış sinyallerle (Ctrl+C gibi) güvenli şekilde durmasını sağlar
        print("\n Durduruluyor...")
        self.running = False

    def cleanup(self):
        # Kaynakları serbest bırakma: FFmpeg'i durdurur, DB bağlantısını kapatır ve pencereleri yok eder
        self.running = False
        if self.process:
            self.process.terminate()
        self.db.close()        
        cv2.destroyAllWindows()
        print("✅ Program sonlandırıldı.")


if __name__ == "__main__":
    # Uygulama başlatıcı
    radar = HavaDurumuRadari()
    radar.run()
