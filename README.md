# 🏙️ Belediye Kamera Takip Sistemi
<img width="812" height="575" alt="Ekran görüntüsü 2026-06-04 212336" src="https://github.com/user-attachments/assets/9e792071-d410-4aa6-8cf0-ddf49f56de23" />

Belediye altyapısına entegre edilmek üzere tasarlanmış, yapay zeka destekli çok modüllü kent kamera analiz platformu. YouTube canlı yayınları ve RTSP kameralardan kişi sayımı, araç takibi, trafik yoğunluk analizi, hava durumu tespiti ve plaka okuma işlevlerini merkezi bir API üzerinden sunar.

---

## 📋 İçindekiler

- [Sistem Özeti](#sistem-özeti)
- [Özellikler](#özellikler)
- [Proje Yapısı](#proje-yapısı)
- [Kullanılan Teknolojiler](#kullanılan-teknolojiler)
- [Kurulum](#kurulum)
- [Veritabanı Kurulumu](#veritabanı-kurulumu)
- [Çalıştırma](#çalıştırma)
- [API Dokümantasyonu](#api-dokümantasyonu)
- [Veritabanı Şeması](#veritabanı-şeması)

---

## Sistem Özeti

Bu sistem, belediye kamera altyapısını (RTSP) veya halka açık YouTube canlı yayınlarını kaynak olarak kullanarak; kişi sayımı, araç takibi, trafik yoğunluğu, hava/görüş koşulları ve plaka tanıma işlemlerini gerçek zamanlı olarak yapar. Tüm veriler PostgreSQL'e kaydedilerek dakikalık/saatlik/günlük raporlar üretilebilir. Arayüz (HTML/C#) ve API birbirinden bağımsız çalışır.

---

## Özellikler

### 👥 Kişi Sayımı

**`1_yt_kisisayma.py`** — YouTube & RTSP kişi sayacı (tam özellikli)
- YOLOv8 ile gerçek zamanlı insan tespiti
- YouTube canlı yayınlarında `yt-dlp` + `ffmpeg` pipeline'ı
- RTSP kamera desteği (TCP transport, otomatik yeniden bağlanma)
- Dakikalık istatistik kayıtları (anlık, ortalama, maksimum, minimum)
- Her 10 saniyede bir anlık ölçüm, dakika sonunda toplu kayıt
- Sinyal yönetimi (SIGINT/SIGTERM) ile güvenli kapatma

**`2_yt_yari_kisisayma.py`** — Yarı optimize sayaç (hafıza dostu)

**`3_ornek_mobes_kisisayma.py`** — Örnek MOBESE kamera entegrasyonu

**`4_ornek_mobes_Idli_kisisayma.py`** — ID tabanlı (re-ID) kişi sayımı (aynı kişiyi tekrar saymama)

**`5_opt_yonlu_Idli_kisisayma.py`** — Yön bazlı (giren/çıkan) optimize sayaç

### 🌤️ Hava Durumu Tespiti

**`6_havadurumu_tespiti_img.py`** — Fotoğraf üzerinde hava durumu analizi
- OpenAI CLIP modeli (`clip-vit-base-patch32`) ile sıfır-shot sınıflandırma
- 7 hava durumu kategorisi: Güneşli, Parçalı Bulutlu, Bulutlu, Yağmurlu, Karlı/Sisli, Gece, Görüş Kısıtlı/Kirli Lens
- Terminal çıktısında yüzdesel karar dağılımı
- Kamera lens kirliliği ve görüş engeli de tespit edilir

**`7_havadurumu_tespiti_vid.py`** — Video/canlı akış üzerinde sürekli hava durumu takibi

### 🚗 Araç Takibi ve Sayımı

**`9_aracTakip.py`** — Gerçek zamanlı araç sayacı
- Özel eğitilmiş YOLOv8 modeli (`arac2.pt`)
- RTSP, YouTube ve yerel video desteği (`yt-dlp` ile çözümleme)
- Araç tipine göre ayrı sınıflandırma ve sayım
- Ekranda kare bazlı araç sayısı paneli
- Oturum sonunda araç tipi bazlı özet rapor
- Çıktı videosu kaydetme seçeneği

### 🚦 Trafik Yoğunluk Analizi

**`10_trafik_yogunluk.py`** — Arka plan çıkarma tabanlı trafik analizi
- YOLOv8 modeli gerektirmez — tamamen görüntü işleme ile çalışır
- Otomatik arka plan öğrenme (ilk 30 kare)
- Piksel değişim oranı ile `SAKIN / NORMAL / YOGUN` üç seviyeli sınıflandırma
- ROI (İlgilenilen Bölge) ayarı ile yol alanına odaklanma
- Sağ alt köşede gerçek zamanlı yoğunluk grafiği
- CLAHE + morfolojik filtre ile gürültü temizleme

### 🔢 Plaka Okuma (ANPR)

**`8_plaka_okuma.py`** — Türkiye plakaları için ANPR sistemi
- İki aşamalı YOLOv8 pipeline: plaka tespiti (`plaka_bulma.pt`) + karakter tanıma (`plaka_okuma.pt`)
- Görüntü ön işleme: CLAHE, bilateral filtre, unsharp masking, adaptif eşikleme
- Akıllı OCR hata düzeltme (harf↔rakam karışıklığı: `0↔O`, `1↔I`, `8↔B`)
- Türkiye'nin 81 il koduna göre format doğrulama
- Türkçe karakter yasağı kontrolü (İ, Ş, Ç, Ğ, Ü, Ö, Q, W, X)
- Sonuçları JSON dosyasına dışa aktarma

### 🌐 Merkezi API

**`api.py`** — FastAPI tabanlı 1139 satırlık ana hub
- Çoklu kamera yönetimi (PostgreSQL'de kayıtlı)
- Dakikalık/saatlik/günlük raporlar
- Canlı MJPEG video stream (araç + trafik)
- SSE (Server-Sent Events) ile gerçek zamanlı istatistik akışı
- Thread tabanlı `StreamWorker` ve `TrafikWorker` mimarisi
- Plaka işleme REST endpoint'i (dosya yükleme)
- Hava durumu geçmişi ve tüm kameralar için tek sorgu
- CSV/JSON veri dışa aktarma
- CORS middleware (web/mobil uyumluluğu)

---

## Proje Yapısı

```
Belediye-Kamera-Takip-Sistemi/
│
├── api.py                          # Ana FastAPI uygulaması (merkezi hub)
├── database.py                     # Veritabanı bağlantı ve işlem sınıfı
├── database_test.py                # Veritabanı bağlantı test scripti
│
├── 1_yt_kisisayma.py               # YouTube/RTSP kişi sayacı (tam özellikli)
├── 2_yt_yari_kisisayma.py          # Yarı optimize kişi sayacı
├── 3_ornek_mobes_kisisayma.py      # MOBESE kamera entegrasyon örneği
├── 4_ornek_mobes_Idli_kisisayma.py # ID tabanlı kişi sayacı (re-ID)
├── 5_opt_yonlu_Idli_kisisayma.py   # Yön bazlı optimize sayaç
│
├── 6_havadurumu_tespiti_img.py     # Fotoğrafta hava durumu tespiti (CLIP)
├── 7_havadurumu_tespiti_vid.py     # Video/canlı akışta hava durumu tespiti
│
├── 8_plaka_okuma.py                # Türk plaka ANPR sistemi
├── 9_aracTakip.py                  # Araç sayacı ve takip
├── 10_trafik_yogunluk.py           # Arka plan çıkarma ile trafik analizi
│
├── Arayuz/                         # Web arayüzü (HTML/C#)
└── README.md
```

---

## Kullanılan Teknolojiler

| Katman | Teknoloji |
|--------|-----------|
| Dil | Python 3.x |
| Görüntü İşleme | OpenCV, NumPy |
| Nesne/Araç/Plaka Tespiti | YOLOv8 (Ultralytics) |
| Görüntü Sınıflandırma | Hugging Face Transformers (CLIP) |
| Video Stream Çözümleme | yt-dlp, ffmpeg |
| Web API | FastAPI + Uvicorn |
| Gerçek Zamanlı Stream | MJPEG (video), SSE (istatistik) |
| Veritabanı | PostgreSQL |
| DB Sürücüsü | psycopg 3 |
| Web Arayüzü | HTML + C# |

---

## Kurulum

### Gereksinimler

```bash
pip install ultralytics opencv-python numpy
pip install fastapi uvicorn psycopg[binary] python-dotenv
pip install transformers torch pillow
pip install yt-dlp
```

> **Not:** `ffmpeg`'in sistem PATH'inde kurulu olması gerekir. İndir: https://ffmpeg.org/download.html

### Model Dosyaları

Aşağıdaki model dosyalarını proje kök dizinine yerleştirin:

| Dosya | Kullanım |
|-------|----------|
| `yolov8n.pt` | Kişi sayımı (YOLO n modeli) |
| `arac2.pt` | Araç tespiti ve sayımı |
| `plaka_bulma.pt` | Araçtaki plakayı bul |
| `plaka_okuma.pt` | Plakadaki karakterleri oku |

---

## Veritabanı Kurulumu

### PostgreSQL'de veritabanı oluşturun:

```sql
CREATE DATABASE belediye_kamera_db;
```

### Tablolar sistem ilk çalıştığında otomatik oluşturulur. Elle oluşturmak için:

```sql
-- Kamera tanımları
CREATE TABLE kameralar (
    id SERIAL PRIMARY KEY,
    ad VARCHAR(100),
    konum VARCHAR(200),
    rtsp_url TEXT,
    aktif BOOLEAN DEFAULT true,
    olusturma_tarihi TIMESTAMP DEFAULT NOW()
);

-- Dakikalık ölçümler
CREATE TABLE dakikalik_olculer (
    id SERIAL PRIMARY KEY,
    kamera_id INTEGER REFERENCES kameralar(id),
    baslangic_zamani TIMESTAMP,
    bitis_zamani TIMESTAMP,
    toplam_kisi INTEGER,
    ortalama_kisi FLOAT,
    maksimum_kisi INTEGER,
    minimum_kisi INTEGER,
    detaylar JSONB
);

-- Anlık ölçümler
CREATE TABLE anlik_olcumler (
    id SERIAL PRIMARY KEY,
    kamera_id INTEGER REFERENCES kameralar(id),
    olcum_zamani TIMESTAMP DEFAULT NOW(),
    anlik_kisi INTEGER
);

-- Hava durumu kayıtları
CREATE TABLE hava_durumu (
    id SERIAL PRIMARY KEY,
    kamera_id INTEGER REFERENCES kameralar(id),
    durum VARCHAR(50),
    guven_orani FLOAT,
    tespit_zamani TIMESTAMP DEFAULT NOW()
);
```

### Bağlantı yapılandırması:

Projede veritabanı bağlantısı `database.py` ve `api.py` içinde tanımlıdır. Kendi sunucunuza göre güncelleyin:

```python
PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'SIFRENIZ',
    'port': 5432
}
```

---

## Çalıştırma

### 1. API Sunucusunu Başlatın

```bash
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

Swagger dokümantasyonu: `http://localhost:8000/docs`

### 2. Sisteme Kamera Ekleyin

API çalışırken bir YouTube canlı yayını veya RTSP kamera ekleyin:

```bash
# YouTube canlı yayını eklemek için:
curl -X POST "http://localhost:8000/youtube-ekle?ad=Merkez+Meydani&konum=Merkez&youtube_url=https://youtube.com/watch?v=..."

# Gerçek RTSP kamera:
# rtsp_url alanını kamera IP adresiyle güncelleyin
```

### 3. Kişi Sayımını Başlatın

```bash
# YouTube'dan sayım:
python 1_yt_kisisayma.py

# Kaynak tipini dosyada değiştirmek için:
# KAYNAK_TIPI = "youtube"  # veya "rtsp"
# YOUTUBE_URL = "https://www.youtube.com/watch?v=..."
# RTSP_URL = "rtsp://kamera.belediye.gov.tr:554/stream"
# KAMERA_ID = 1  # Veritabanındaki kamera ID'si
```

### 4. Araç Takibini Başlatın

```bash
python 9_aracTakip.py
# Program başlayınca RTSP veya YouTube URL girmeniz istenir
```

### 5. Trafik Yoğunluk Analizini Başlatın

```bash
python 10_trafik_yogunluk.py
# Program başlayınca HLS (m3u8) veya RTSP URL girmeniz istenir
```

### 6. Hava Durumu Tespiti

```bash
# Fotoğraf üzerinde:
python 6_havadurumu_tespiti_img.py
# FOTOGRAF_YOLU değişkenini dosyada güncelleyin

# Video/canlı akış üzerinde:
python 7_havadurumu_tespiti_vid.py
```

### 7. Plaka Okuma

```bash
python 8_plaka_okuma.py
# TEST_FOLDER klasörüne test resimlerini koyun
# Sonuçlar results/plaka_sonuclari.json dosyasına yazılır
```

---

## API Dokümantasyonu

### Kamera Yönetimi

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/kameralar` | Tüm aktif kameraları listele |
| GET | `/api/kameralar` | API formatında kamera listesi |
| POST | `/youtube-ekle` | Yeni YouTube/RTSP kamera ekle |

### Kişi Sayımı

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/son-dakika/{kamera_id}` | Son dakika ölçümü |
| GET | `/api/son-dakika?kamera_id=1` | API formatında son dakika |
| GET | `/canli/{kamera_id}` | Son 10 anlık ölçüm |
| GET | `/api/canli-veri?kamera_id=1` | API formatında canlı veri |
| GET | `/tum-dakikalar/{kamera_id}` | Tüm dakika kayıtları |
| GET | `/saatlik-rapor/{kamera_id}?tarih=2025-01-01` | Saatlik özet |
| GET | `/gunluk-rapor/{kamera_id}?baslangic=...&bitis=...` | Günlük rapor |
| GET | `/veri-export/{kamera_id}?format=csv` | CSV/JSON dışa aktarım |

### Araç Takibi

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/arac-video-stream?kaynak=URL` | MJPEG canlı video akışı |
| GET | `/api/arac-istatistik-stream?kaynak=URL` | SSE istatistik akışı |
| DELETE | `/api/arac-stream-durdur?kaynak=URL` | Stream durdur ve kaydet |

### Trafik Yoğunluk

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/trafik-stream?kaynak=URL` | MJPEG trafik analiz akışı |
| GET | `/api/trafik-istatistik-stream?kaynak=URL` | SSE trafik istatistik akışı |
| DELETE | `/api/trafik-stream-durdur?kaynak=URL` | Trafik stream durdur |

### Hava Durumu

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/hava-durumu/{kamera_id}` | Bir kameranın son hava durumu |
| GET | `/hava-durumu-gecmis/{kamera_id}?tarih=...` | Günlük hava durumu geçmişi |
| GET | `/hava-durumu-tum-kameralar` | Tüm kameraların son durumu |
| GET | `/api/hava-durumu/son?kamera_id=1` | API formatında son durum |

### Plaka

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| POST | `/plaka/isle` | Görüntü yükle, plakaları oku |

### Sistem

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/` | API bilgileri ve endpoint listesi |
| DELETE | `/veri-temizle/{gun}` | Eski kayıtları arka planda temizle |

---

## Veritabanı Şeması

```
kameralar           → Kayıtlı kamera tanımları (RTSP URL, konum, durum)
dakikalik_olculer   → Dakika bazlı kişi sayımı (toplam, ort, maks, min, detaylar JSONB)
anlik_olcumler      → 10 saniyede bir anlık kişi sayısı
hava_durumu         → Kamera başına hava/görüş koşulu kayıtları
```

---

## Mimari Genel Bakış

```
┌──────────────────────────────────────────────────────────────┐
│                    api.py (FastAPI :8000)                     │
│  /kameralar  /canli  /saatlik  /arac-stream  /trafik-stream  │
│  /hava-durumu  /plaka  /veri-export                          │
└────────┬──────────┬──────────┬──────────┬────────────────────┘
         │          │          │          │
    ┌────┘   ┌──────┘   ┌──────┘   ┌──────┘
    ▼        ▼          ▼          ▼
 Kişi     StreamWorker TrafikWorker  Plaka
 Sayımı   (araç, MJPEG) (trafik,MJPEG) Sistemi
 (YOLO)   (thread)    (thread)     (2x YOLO)
    │        │          │          │
    └────────┴──────────┴──────────┘
                    │
              PostgreSQL
           (belediye_kamera_db)
```

Tüm stream worker'ları arka plan thread'lerinde bağımsız çalışır. API'nin async loop'u bloklanmaz. Her kaynak URL için tek bir worker örneği çalışır; birden fazla istemci aynı stream'i paylaşır.

---

## Lisans

Bu proje eğitim amaçlı geliştirilmiştir.
