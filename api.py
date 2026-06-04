# api.py

# Uvicorn ile çalıştırmak için:
# C:\Users\EXCALIBUR\AppData\Local\spyder-6\envs\spyder-runtime\python.exe -m uvicorn api:app --reload --host 0.0.0.0 --port 8000


from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from datetime import datetime
from typing import Optional
import psycopg
from psycopg.rows import dict_row
import json
import csv
import io
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends, UploadFile, File
import numpy as np
import cv2
import tempfile
import os
from plaka_sistemi import TurkishPlateSystem
from ultralytics import YOLO  # ⬅️ ŞU ÖNEMLİ
import yt_dlp  # ⬅️ ŞU ÖNEMLİ
import asyncio
import time
import threading
from database import DatabaseManager

db = DatabaseManager({
    "host":     "localhost",
    "database": "belediye_kamera_db",
    "user":     "postgres",
    "password": "Hello",
    "port":     5432
})
db.connect()


app = FastAPI(
    title="Belediye Kamera Takip API",
    description="YouTube canlı yayınları ve kameralardan kişi sayımı API'si",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Veritabanı bağlantı fonksiyonu (psycopg 3 ile düzeltildi)
def get_db():
    conn = psycopg.connect(
        host="localhost",
        dbname="belediye_kamera_db",
        user="postgres",
        password="Hello",
        row_factory=dict_row  # RealDictCursor'ın yerini alır
    )
    try:
        yield conn
    finally:
        conn.close()

@app.get("/")
def root():
    return {
        "api": "Belediye Kamera Takip Sistemi",
        "versiyon": "1.0",
        "kaynak_tipi": "YouTube Canlı Yayın (Test)",
        "endpoints": [
            "/kameralar",
            "/api/kameralar",
            "/son-dakika/{kamera_id}",
            "/saatlik-rapor/{kamera_id}",
            "/gunluk-rapor/{kamera_id}",
            "/canli/{kamera_id}",
            "/api/canli-veri",
            "/youtube-ekle",
            "/veri-export"
        ]
    }

@app.get("/kameralar")
def get_kameralar(conn=Depends(get_db)):
    """Tüm kameraları listele"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ad, konum, rtsp_url as kaynak_url, aktif, olusturma_tarihi 
            FROM kameralar 
            WHERE aktif = true
            ORDER BY id
        """)
        return cur.fetchall()

# ⬇️ ŞU SATIR EKLE (MVC için)
@app.get("/api/kameralar")
def get_api_kameralar(conn=Depends(get_db)):
    """API formatında tüm kameraları listele"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, ad, konum, rtsp_url as kaynak_url, aktif, olusturma_tarihi 
            FROM kameralar 
            WHERE aktif = true
            ORDER BY id
        """)
        return cur.fetchall()

@app.post("/youtube-ekle")
def youtube_kamera_ekle(
    ad: str,
    konum: str,
    youtube_url: str,
    conn=Depends(get_db)
):
    """YouTube canlı yayınını kamera olarak ekle"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO kameralar (ad, konum, rtsp_url, aktif)
            VALUES (%s, %s, %s, true)
            RETURNING id
        """, (ad, konum, youtube_url))
        kamera_id = cur.fetchone()['id']
        conn.commit()
    
    return {
        "mesaj": "YouTube canlı yayını eklendi",
        "kamera_id": kamera_id,
        "not": "Bu bir test kaynağıdır. Gerçek kameraya geçerken rtsp_url'i güncelleyin."
    }

@app.get("/son-dakika/{kamera_id}")
def son_dakika_verisi(kamera_id: int, conn=Depends(get_db)):
    """Son dakika verisini getir"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM dakikalik_olculer 
            WHERE kamera_id = %s 
            ORDER BY baslangic_zamani DESC 
            LIMIT 1
        """, (kamera_id,))
        sonuc = cur.fetchone()
        
        if not sonuc:
            raise HTTPException(status_code=404, detail="Veri bulunamadı")
        
        # Kamera bilgisini de ekle
        cur.execute("SELECT ad, konum, rtsp_url FROM kameralar WHERE id = %s", (kamera_id,))
        kamera = cur.fetchone()
        
        return {
            "kamera": kamera['ad'],
            "konum": kamera['konum'],
            "kaynak": "YouTube" if "youtube" in kamera['rtsp_url'] else "RTSP",
            "veri": sonuc
        }

# ⬇️ EKLENDİ (MVC için - query param'lı /api/son-dakika endpoint'i)
@app.get("/api/son-dakika")
def api_son_dakika(kamera_id: int, conn=Depends(get_db)):
    """API formatında son dakika verisi"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM dakikalik_olculer 
            WHERE kamera_id = %s 
            ORDER BY baslangic_zamani DESC 
            LIMIT 1
        """, (kamera_id,))
        sonuc = cur.fetchone()

        if not sonuc:
            raise HTTPException(status_code=404, detail="Veri bulunamadı")

        cur.execute("SELECT ad, konum, rtsp_url FROM kameralar WHERE id = %s", (kamera_id,))
        kamera = cur.fetchone()

        return {
            "kamera": kamera['ad'],
            "konum": kamera['konum'],
            "kaynak": "YouTube" if "youtube" in kamera['rtsp_url'] else "RTSP",
            "veri": sonuc
        }

@app.get("/saatlik-rapor/{kamera_id}")
def saatlik_rapor(
    kamera_id: int, 
    tarih: Optional[str] = None,
    conn=Depends(get_db)
):
    """Saatlik yoğunluk raporu (Farklı Kişi Sayılarına Göre)"""
    if not tarih:
        tarih = datetime.now().strftime("%Y-%m-%d")
    
    with conn.cursor() as cur:
        # DÜZELTME: SUM(toplam_kisi) yerine SUM(farkli_kisi_sayisi) alınıyor
        cur.execute("""
            SELECT 
                date_trunc('hour', baslangic_zamani) as saat,
                COUNT(*) as dakika_sayisi,
                SUM(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as toplam_kisi,
                ROUND(AVG(ortalama_kisi)::numeric, 2) as ortalama_kisi,
                MAX(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as pik_kisi
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
                AND baslangic_zamani::date = %s::date
            GROUP BY saat
            ORDER BY saat
        """, (kamera_id, tarih))
        
        sonuclar = cur.fetchall()
        
        # Özet bilgi: Tüm saatlerdeki farklı kişilerin toplamı
        toplam = sum([s['toplam_kisi'] for s in sonuclar]) if sonuclar else 0
        
        return {
            "tarih": tarih,
            "toplam_kisi": toplam,
            "saatlik_detay": sonuclar
        }

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/saatlik-rapor")
def api_saatlik_rapor(
    kamera_id: int,
    tarih: Optional[str] = None,
    conn=Depends(get_db)
):
    """API formatında saatlik yoğunluk raporu"""
    if not tarih:
        tarih = datetime.now().strftime("%Y-%m-%d")
    
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                date_trunc('hour', baslangic_zamani) as saat,
                COUNT(*) as dakika_sayisi,
                SUM(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as toplam_kisi,
                ROUND(AVG(ortalama_kisi)::numeric, 2) as ortalama_kisi,
                MAX(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as pik_kisi
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
                AND baslangic_zamani::date = %s::date
            GROUP BY saat
            ORDER BY saat
        """, (kamera_id, tarih))
        
        sonuclar = cur.fetchall()
        toplam = sum([s['toplam_kisi'] for s in sonuclar]) if sonuclar else 0
        
        return {
            "tarih": tarih,
            "toplam_kisi": toplam,
            "saatlik_detay": sonuclar
        }

@app.get("/gunluk-rapor/{kamera_id}")
def gunluk_rapor(
    kamera_id: int,
    baslangic: str,
    bitis: str,
    conn=Depends(get_db)
):
    """Günlük rapor (Farklı Kişi Sayılarına Göre)"""
    with conn.cursor() as cur:
        # DÜZELTME: Günlük toplamda da farklı kişileri topluyoruz
        cur.execute("""
            SELECT 
                baslangic_zamani::date as gun,
                COUNT(*) as olcum_sayisi,
                SUM(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as gunluk_toplam,
                ROUND(AVG(ortalama_kisi)::numeric, 2) as gunluk_ortalama
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
                AND baslangic_zamani::date BETWEEN %s::date AND %s::date
            GROUP BY gun
            ORDER BY gun
        """, (kamera_id, baslangic, bitis))
        
        return {
            "baslangic": baslangic,
            "bitis": bitis,
            "gunluk_rapor": cur.fetchall()
        }

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/gunluk-rapor")
def api_gunluk_rapor(
    kamera_id: int,
    baslangic: str,
    bitis: str,
    conn=Depends(get_db)
):
    """API formatında günlük rapor"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                baslangic_zamani::date as gun,
                COUNT(*) as olcum_sayisi,
                SUM(COALESCE(CAST(detaylar->>'farkli_kisi_sayisi' AS INTEGER), 0)) as gunluk_toplam,
                ROUND(AVG(ortalama_kisi)::numeric, 2) as gunluk_ortalama
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
                AND baslangic_zamani::date BETWEEN %s::date AND %s::date
            GROUP BY gun
            ORDER BY gun
        """, (kamera_id, baslangic, bitis))
        
        return {
            "baslangic": baslangic,
            "bitis": bitis,
            "gunluk_rapor": cur.fetchall()
        }

@app.get("/tum-dakikalar/{kamera_id}")
def tum_dakikalar(
    kamera_id: int, 
    limit: int = Query(100, ge=1, le=1000),
    conn=Depends(get_db)
):
    """Tüm dakika verilerini listele (son 100 kayıt)"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id,
                baslangic_zamani,
                bitis_zamani,
                toplam_kisi,
                ortalama_kisi,
                maksimum_kisi,
                minimum_kisi,
                detaylar->>'farkli_kisi_sayisi' as farkli_kisi,
                detaylar->>'kisi_id_listesi' as kisi_idleri
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
            ORDER BY baslangic_zamani DESC 
            LIMIT %s
        """, (kamera_id, limit))
        
        sonuclar = cur.fetchall()
        
        # Kamera bilgisini de ekle
        cur.execute("SELECT ad, konum FROM kameralar WHERE id = %s", (kamera_id,))
        kamera = cur.fetchone()
        
        return {
            "kamera": kamera['ad'] if kamera else "Bilinmiyor",
            "konum": kamera['konum'] if kamera else "Bilinmiyor",
            "toplam_kayit": len(sonuclar),
            "dakikalar": sonuclar
        }

@app.get("/canli/{kamera_id}")
def canli_veri(
    kamera_id: int, 
    limit: int = Query(10, ge=1, le=100),
    conn=Depends(get_db)
):
    """Canlı anlık veriler"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM anlik_olcumler 
            WHERE kamera_id = %s 
            ORDER BY olcum_zamani DESC 
            LIMIT %s
        """, (kamera_id, limit))
        
        return {
            "kamera_id": kamera_id,
            "son_veriler": cur.fetchall()
        }

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/canli-veri")
def api_canli_veri(
    kamera_id: int,
    limit: int = Query(10, ge=1, le=100),
    conn=Depends(get_db)
):
    """API formatında canlı anlık veriler"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT * FROM anlik_olcumler 
            WHERE kamera_id = %s 
            ORDER BY olcum_zamani DESC 
            LIMIT %s
        """, (kamera_id, limit))
        
        return {
            "kamera_id": kamera_id,
            "son_veriler": cur.fetchall()
        }

@app.get("/veri-export/{kamera_id}")
def veri_export(
    kamera_id: int,
    baslangic: str,
    bitis: str,
    format: str = Query("json", pattern="^(json|csv)$"),
    conn=Depends(get_db)
):
    """Verileri dışa aktar (JSON/CSV)"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                baslangic_zamani,
                bitis_zamani,
                toplam_kisi,
                ortalama_kisi,
                maksimum_kisi,
                minimum_kisi
            FROM dakikalik_olculer 
            WHERE kamera_id = %s 
                AND baslangic_zamani::date BETWEEN %s::date AND %s::date
            ORDER BY baslangic_zamani
        """, (kamera_id, baslangic, bitis))
        
        veriler = cur.fetchall()
        
        if format == "json":
            return {"kamera_id": kamera_id, "veriler": veriler}
        else:
            # CSV formatı
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['baslangic', 'bitis', 'toplam_kisi', 'ortalama', 'maks', 'min'])
            for v in veriler:
                writer.writerow([
                    v['baslangic_zamani'],
                    v['bitis_zamani'],
                    v['toplam_kisi'],
                    v['ortalama_kisi'],
                    v['maksimum_kisi'],
                    v['minimum_kisi']
                ])
            
            return StreamingResponse(
                io.BytesIO(output.getvalue().encode()),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=rapor_{kamera_id}.csv"}
            )

@app.delete("/veri-temizle/{gun}")
def eski_verileri_temizle(
    gun: int = 30,
    background_tasks: BackgroundTasks = None,
    conn=Depends(get_db)
):
    """Eski verileri temizle (background'da çalışır)"""
    def temizleme_gorevi():
        with psycopg.connect(
            host="localhost",
            dbname="belediye_kamera_db",
            user="postgres",
            password="Hello"
        ) as temp_conn:
            with temp_conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM dakikalik_olculer 
                    WHERE baslangic_zamani < NOW() - INTERVAL '%s days'
                """, (gun,))
                silinen = cur.rowcount
                temp_conn.commit()
                print(f"🧹 {silinen} eski kayıt silindi")
    
    if background_tasks:
        background_tasks.add_task(temizleme_gorevi)
        return {"mesaj": f"{gun} günden eski veriler siliniyor (background)"}
    else:
        return {"mesaj": "Background tasks desteklenmiyor"}
    
@app.get("/hava-durumu/{kamera_id}")
def son_hava_durumu(kamera_id: int, conn=Depends(get_db)):
    """Bir kameranın en son tespit edilen hava durumunu getirir."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT durum, guven_orani, tespit_zamani
            FROM hava_durumu
            WHERE kamera_id = %s
            ORDER BY tespit_zamani DESC
            LIMIT 1
        """, (kamera_id,))
        sonuc = cur.fetchone()
 
        if not sonuc:
            raise HTTPException(status_code=404, detail="Bu kamera için hava durumu verisi yok")
 
        return {
            "kamera_id": kamera_id,
            "durum":        sonuc["durum"],
            "guven_orani":  sonuc["guven_orani"],
            "tespit_zamani": sonuc["tespit_zamani"]
        }

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/hava-durumu/son")
def api_son_hava_durumu(kamera_id: int, conn=Depends(get_db)):
    """API formatında son hava durumu"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT durum, guven_orani, tespit_zamani
            FROM hava_durumu
            WHERE kamera_id = %s
            ORDER BY tespit_zamani DESC
            LIMIT 1
        """, (kamera_id,))
        sonuc = cur.fetchone()
 
        if not sonuc:
            raise HTTPException(status_code=404, detail="Bu kamera için hava durumu verisi yok")
 
        return {
            "kamera_id": kamera_id,
            "durum": sonuc["durum"],
            "guven_orani": sonuc["guven_orani"],
            "tespit_zamani": sonuc["tespit_zamani"]
        }
 
@app.get("/hava-durumu-gecmis/{kamera_id}")
def hava_durumu_gecmis(
    kamera_id: int,
    tarih: Optional[str] = None,
    conn=Depends(get_db)
):
    """
    Bir kameranın günlük hava durumu geçmişini getirir.
    tarih parametresi verilmezse bugün kullanılır (YYYY-MM-DD formatında).
    """
    if not tarih:
        tarih = datetime.now().strftime("%Y-%m-%d")
 
    with conn.cursor() as cur:
        cur.execute("""
            SELECT durum, guven_orani, tespit_zamani
            FROM hava_durumu
            WHERE kamera_id = %s
                AND tespit_zamani::date = %s::date
            ORDER BY tespit_zamani ASC
        """, (kamera_id, tarih))
        kayitlar = cur.fetchall()
 
        # Saatlik dağılım özeti — hangi durumdan kaç kez geçildi
        from collections import Counter
        ozet = dict(Counter(k["durum"] for k in kayitlar))
 
        return {
            "kamera_id":  kamera_id,
            "tarih":      tarih,
            "toplam_degisim": len(kayitlar),
            "durum_ozeti": ozet,
            "gecmis":     kayitlar
        }

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/hava-durumu/gecmis")
def api_hava_durumu_gecmis(
    kamera_id: int,
    tarih: Optional[str] = None,
    conn=Depends(get_db)
):
    """API formatında hava durumu geçmişi"""
    if not tarih:
        tarih = datetime.now().strftime("%Y-%m-%d")
 
    with conn.cursor() as cur:
        cur.execute("""
            SELECT durum, guven_orani, tespit_zamani
            FROM hava_durumu
            WHERE kamera_id = %s
                AND tespit_zamani::date = %s::date
            ORDER BY tespit_zamani ASC
        """, (kamera_id, tarih))
        kayitlar = cur.fetchall()
 
        from collections import Counter
        ozet = dict(Counter(k["durum"] for k in kayitlar))
 
        return {
            "kamera_id":  kamera_id,
            "tarih":      tarih,
            "toplam_degisim": len(kayitlar),
            "durum_ozeti": ozet,
            "gecmis":     kayitlar
        }
 
@app.get("/hava-durumu-tum-kameralar")
def tum_kameralar_hava_durumu(conn=Depends(get_db)):
    """Sistemdeki tüm aktif kameraların son hava durumunu tek sorguda getirir."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (h.kamera_id)
                h.kamera_id,
                k.ad        AS kamera_ad,
                k.konum,
                h.durum,
                h.guven_orani,
                h.tespit_zamani
            FROM hava_durumu h
            JOIN kameralar k ON k.id = h.kamera_id
            WHERE k.aktif = true
            ORDER BY h.kamera_id, h.tespit_zamani DESC
        """)
        return cur.fetchall()

# ⬇️ ŞU SATIR EKLE (MVC için - API formatında)
@app.get("/api/hava-durumu/tum-kameralar")
def api_tum_kameralar_hava_durumu(conn=Depends(get_db)):
    """API formatında tüm kameraların hava durumu"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (h.kamera_id)
                h.kamera_id,
                k.ad        AS kamera_ad,
                k.konum,
                h.durum,
                h.guven_orani,
                h.tespit_zamani
            FROM hava_durumu h
            JOIN kameralar k ON k.id = h.kamera_id
            WHERE k.aktif = true
            ORDER BY h.kamera_id, h.tespit_zamani DESC
        """)
        return cur.fetchall()
    
system = TurkishPlateSystem("plaka_bulma.pt", "plaka_okuma.pt")

@app.post("/plaka/isle")
async def plaka_isle(file: UploadFile = File(...)):
    uzanti = os.path.splitext(file.filename)[1].lower()
    if uzanti not in [".jpg", ".jpeg", ".png", ".bmp"]:
        raise HTTPException(status_code=400, detail="Geçersiz dosya formatı")
    with tempfile.NamedTemporaryFile(delete=False, suffix=uzanti) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        img = cv2.imread(tmp_path)
        if img is None:
            raise HTTPException(status_code=400, detail="Görüntü okunamadı")
        sonuclar = []
        detect_results = system.detector(img, verbose=False)
        for res in detect_results:
            for box in res.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf_detect = float(box.conf[0])
                width  = x2 - x1
                height = y2 - y1
                x1 = max(0, x1 - int(width * 0.3))
                x2 = min(img.shape[1], x2 + int(width * 0.3))
                y1 = max(0, y1 - int(height * 0.1))
                y2 = min(img.shape[0], y2 + int(height * 0.1))
                plate_crop = img[y1:y2, x1:x2]
                processed = system.pre_process(plate_crop)
                if processed is None:
                    continue
                ocr_res = system.ocr_model(processed, verbose=False)
                boxes = ocr_res[0].boxes.data.tolist()
                boxes.sort(key=lambda x: x[0])
                raw_text = ""
                for b in boxes:
                    raw_text += system.ocr_model.names[int(b[5])]
                conf_ocr = float(np.mean([b[4] for b in boxes])) if boxes else 0.0
                corrected  = system.correct_ocr_errors(raw_text)
                is_valid, formatted = system.validate_plate(corrected)

                # Veritabanına kaydet
                db.plaka_kaydet(
                    ham          = raw_text,
                    duzeltilmis  = corrected,
                    formatli     = formatted,
                    gecerli      = is_valid,
                    guven_tespit = round(conf_detect, 2),
                    guven_ocr    = round(conf_ocr, 2),
                    dosya_adi    = file.filename
                )

                sonuclar.append({
                    "dosya":            file.filename,
                    "hamMetin":         raw_text,
                    "duzeltilmisMetin": corrected,
                    "formatliPlaka":    formatted,
                    "gecerli":          is_valid,
                    "tespitGuven":      round(conf_detect, 2),
                    "ocrGuven":         round(conf_ocr, 2),
                    "zaman":            datetime.now().isoformat()
                })
        return sonuclar
    finally:
        os.unlink(tmp_path)
        
arac_model = None

# ── Global kare kuyruğu ──────────────────────────────────────
# Her kaynak için ayrı bir worker thread çalışır.
# YOLO işlenmiş JPEG'leri ve istatistikleri bu kuyruktan alırız.
_stream_registry: dict = {}   # kaynak_key → StreamWorker

class StreamWorker:
    """
    Ayrı bir thread'de çalışır:
      - HLS/RTSP'den kare okur
      - N karede bir YOLO uygular
      - JPEG encode eder
      - Son kareyi + istatistiği hafızada tutar (fan-out için)
    """
    YOLO_HER_N_KARE = 3        # Her 3 karede bir YOLO — akıcılık/doğruluk dengesi
    JPEG_KALITE     = 60       # Düşür → daha az bant, daha az gecikme
    MAX_GENISLIK    = 854      # 480p'ye zorla — YOLO + encode hızlanır
    BUFFER_SURE     = 0.03     # ~30 FPS hedefi (saniye)

    def __init__(self, kaynak: str):
        self.kaynak      = kaynak
        self.son_jpeg    = None          # bytes
        self.son_stats   = {}            # dict
        self.kare_no     = 0
        self.aktif       = True
        self._lock       = threading.Lock()
        self._thread     = threading.Thread(target=self._calis, daemon=True)
        self._thread.start()

    def _kaynak_ac(self):
        k = self.kaynak
        if "youtube" in k.lower() or "youtu.be" in k.lower() or "m3u8" not in k.lower():
            # Eğer doğrudan m3u8 değil ama YouTube/genel link ise yt-dlp ile çöz
            try:
                ydl_opts = {"format": "best[height<=480]/best", "quiet": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(k, download=False)
                    k = info["url"]
            except Exception:
                pass  # Direkt dene

        cap = cv2.VideoCapture(k)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        return cap

    def _calis(self):
        global arac_model
        if arac_model is None:
            arac_model = YOLO("arac2.pt")

        renkler = [
            (0, 120, 255), (0, 210, 100), (255, 80, 0),
            (180, 0, 255), (0, 220, 220), (255, 200, 0),
        ]

        cap = self._kaynak_ac()
        if not cap.isOpened():
            self.aktif = False
            return

        en_yuksek   = {}
        son_kutular = []   # son YOLO sonucunu sakla (atlanan karelere de çiz)

        while self.aktif:
            t0 = time.time()

            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            self.kare_no += 1

            # Küçült — hem YOLO hem encode hızlanır
            h, w = frame.shape[:2]
            if w > self.MAX_GENISLIK:
                oran   = self.MAX_GENISLIK / w
                frame  = cv2.resize(frame, (self.MAX_GENISLIK, int(h * oran)),
                                    interpolation=cv2.INTER_LINEAR)

            # YOLO — her N karede bir
            kare_say = {}
            if self.kare_no % self.YOLO_HER_N_KARE == 0:
                results     = arac_model(frame, conf=0.4, verbose=False, imgsz=416)[0]
                son_kutular = []
                for box in results.boxes:
                    cls_id   = int(box.cls[0])
                    cls_name = arac_model.names[cls_id]
                    guven    = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    son_kutular.append((cls_id, cls_name, guven, x1, y1, x2, y2))
                    kare_say[cls_name] = kare_say.get(cls_name, 0) + 1
                for cls, cnt in kare_say.items():
                    en_yuksek[cls] = max(en_yuksek.get(cls, 0), cnt)
            else:
                # Atlanan karede önceki sayımı kullan
                for _, cls_name, _, _, _, _, _ in son_kutular:
                    kare_say[cls_name] = kare_say.get(cls_name, 0) + 1

            # Kutuları çiz (son YOLO sonucunu kullan)
            for cls_id, cls_name, guven, x1, y1, x2, y2 in son_kutular:
                renk = renkler[cls_id % len(renkler)]
                cv2.rectangle(frame, (x1, y1), (x2, y2), renk, 2)
                etiket = f"{cls_name} {guven:.0%}"
                (tw, th), _ = cv2.getTextSize(etiket, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), renk, -1)
                cv2.putText(frame, etiket, (x1 + 2, y1 - 3),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # Sol üst panel
            toplam  = sum(kare_say.values())
            satirlar = [f"Toplam: {toplam}"] + \
                       [f"  {k}: {v}" for k, v in sorted(kare_say.items())]
            panel_h = 16 + 18 * len(satirlar)
            cv2.rectangle(frame, (5, 5), (190, panel_h), (0, 0, 0), -1)
            for i, s in enumerate(satirlar):
                cv2.putText(frame, s, (9, 20 + i * 18),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            # JPEG encode
            _, buf = cv2.imencode(
                ".jpg", frame,
                [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_KALITE]
            )

            stats = {
                "kare":              self.kare_no,
                "kare_sayimlari":    kare_say,
                "en_yuksek":         en_yuksek,
                "toplam_su_an":      toplam,
                "toplam_en_yuksek":  sum(en_yuksek.values()),
            }

            with self._lock:
                self.son_jpeg  = buf.tobytes()
                self.son_stats = stats

            # Hedef FPS'e göre bekle
            gecen = time.time() - t0
            bekle = self.BUFFER_SURE - gecen
            if bekle > 0:
                time.sleep(bekle)

        cap.release()

    def son_kare(self):
        with self._lock:
            return self.son_jpeg

    def istatistik(self):
        with self._lock:
            return dict(self.son_stats)

    def durdur(self):
        self.aktif = False


def _worker_al(kaynak: str) -> StreamWorker:
    """Var olan worker'ı döner, yoksa yeni başlatır."""
    if kaynak not in _stream_registry or not _stream_registry[kaynak].aktif:
        _stream_registry[kaynak] = StreamWorker(kaynak)
    return _stream_registry[kaynak]


@app.get("/api/arac-video-stream")
async def arac_video_stream(kaynak: str = Query(...)):
    """MJPEG stream — worker thread'den son kareyi çeker, async loop bloklanmaz."""
    worker = _worker_al(kaynak)

    async def generate():
        while worker.aktif:
            jpeg = worker.son_kare()
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    jpeg +
                    b"\r\n"
                )
            await asyncio.sleep(0.033)   # ~30 FPS

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",     # nginx varsa buffer'ı kapat
        }
    )


@app.get("/api/arac-istatistik-stream")
async def arac_istatistik_stream(kaynak: str = Query(...)):
    """SSE istatistik akışı — aynı worker'dan istatistik çeker."""
    worker = _worker_al(kaynak)

    async def generator():
        son_kare_no = -1
        while worker.aktif:
            stats = worker.istatistik()
            # Sadece yeni kare gelince gönder
            if stats and stats.get("kare", 0) != son_kare_no:
                son_kare_no = stats["kare"]
                yield f"data: {json.dumps(stats)}\n\n"
            await asyncio.sleep(0.1)   # 10 Hz istatistik güncellemesi yeterli

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.delete("/api/arac-stream-durdur")
async def arac_stream_durdur(kaynak: str = Query(...)):
    if kaynak in _stream_registry:
        worker = _stream_registry[kaynak]
        stats  = worker.istatistik()
        if stats:
            db.arac_sayim_kaydet(
                kaynak          = kaynak,
                toplam          = stats.get("toplam_en_yuksek", 0),
                sinif_sayimlari = stats.get("en_yuksek", {}),
                islenen_kare    = stats.get("kare", 0)
            )
        worker.durdur()
        del _stream_registry[kaynak]
    return {"tamam": True}



# Trafik Yoğunluk Worker:
trafik_registry: dict = {}

class TrafikWorker:
    JPEG_KALITE  = 60
    MAX_GENISLIK = 960
    ARKAPLAN_KARE_SAYISI = 30
    DEGISIM_ESIGI = 35
    YOGUN_ESIK    = 0.18
    NORMAL_ESIK   = 0.09

    def __init__(self, kaynak: str):
        self.kaynak   = kaynak
        self.son_jpeg = None
        self.son_stats = {}
        self.kare_no  = 0
        self.aktif    = True
        self._lock    = threading.Lock()
        self._thread  = threading.Thread(target=self._calis, daemon=True)
        self._thread.start()

    def _kaynak_coz(self):
        k = self.kaynak
        if k.startswith("rtsp://") or k.endswith(".m3u8") or "m3u8" in k:
            return k
        try:
            ydl_opts = {"format": "best[height<=480]/best", "quiet": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(k, download=False)
                return info.get("url") or info["formats"][-1]["url"]
        except:
            return k

    def _yogunluk_etiketi(self, oran):
        if oran >= self.YOGUN_ESIK:
            return "YOGUN",   (0, 0, 220)
        elif oran >= self.NORMAL_ESIK:
            return "NORMAL",  (0, 165, 255)
        else:
            return "SAKIN",   (0, 200, 80)

    def _calis(self):
        url = self._kaynak_coz()
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        if not cap.isOpened():
            self.aktif = False
            return

        arkaplan_buf = []
        arkaplan     = None
        gecmis       = []
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

        while self.aktif:
            ret, kare = cap.read()
            if not ret:
                time.sleep(0.05)
                continue

            self.kare_no += 1

            h, w = kare.shape[:2]
            if w > self.MAX_GENISLIK:
                oran = self.MAX_GENISLIK / w
                kare = cv2.resize(kare, (self.MAX_GENISLIK, int(h * oran)))

            gri = cv2.cvtColor(kare, cv2.COLOR_BGR2GRAY)
            gri = cv2.GaussianBlur(gri, (5, 5), 0)

            # ROI
            rh, rw = gri.shape
            roi = gri[int(0.15*rh):int(0.95*rh), int(0.05*rw):int(0.95*rw)]

            # Arka plan öğrenme
            if len(arkaplan_buf) < self.ARKAPLAN_KARE_SAYISI:
                arkaplan_buf.append(roi.astype(np.float32))
                # Öğrenme ekranı
                ilerleme = int((len(arkaplan_buf) / self.ARKAPLAN_KARE_SAYISI) * 100)
                cv2.rectangle(kare, (20, 20), (400, 60), (0, 0, 0), -1)
                cv2.putText(kare, f"Arka plan ogreniliyor... %{ilerleme}",
                            (30, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
                _, buf = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_KALITE])
                with self._lock:
                    self.son_jpeg  = buf.tobytes()
                    self.son_stats = {"ogreniliyor": True, "ilerleme": ilerleme}
                continue

            if arkaplan is None:
                arkaplan = np.mean(arkaplan_buf, axis=0).astype(np.float32)

            # Fark hesapla
            fark = cv2.absdiff(arkaplan, roi.astype(np.float32)).astype(np.uint8)
            _, maske = cv2.threshold(fark, self.DEGISIM_ESIGI, 255, cv2.THRESH_BINARY)
            maske = cv2.morphologyEx(maske, cv2.MORPH_OPEN,  kernel)
            maske = cv2.morphologyEx(maske, cv2.MORPH_CLOSE, kernel)

            degisen = np.count_nonzero(maske)
            oran    = degisen / maske.size
            gecmis.append(oran)
            if len(gecmis) > 150:
                gecmis.pop(0)

            etiket, renk = self._yogunluk_etiketi(oran)

            # ROI dikdörtgeni
            h2, w2 = kare.shape[:2]
            cv2.rectangle(kare,
                          (int(0.05*w2), int(0.15*h2)),
                          (int(0.95*w2), int(0.95*h2)),
                          renk, 2)

            # Bilgi paneli
            cv2.rectangle(kare, (5, 5), (260, 90), (0, 0, 0), -1)
            cv2.putText(kare, etiket, (15, 42),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, renk, 3)
            cv2.putText(kare, f"Degisim: %{oran*100:.1f}", (15, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)
            cv2.putText(kare, f"Kare: {self.kare_no}", (15, 82),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)

            # Hareket maskesi sağ üst
            mask_kucuk  = cv2.resize(maske, (160, 90))
            mask_renkli = cv2.cvtColor(mask_kucuk, cv2.COLOR_GRAY2BGR)
            kare[10:100, w2-170:w2-10] = mask_renkli
            cv2.putText(kare, "Hareket maskesi", (w2-168, 108),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)

            _, buf = cv2.imencode(".jpg", kare, [cv2.IMWRITE_JPEG_QUALITY, self.JPEG_KALITE])

            ortalama = float(np.mean(gecmis)) if gecmis else 0.0

            with self._lock:
                self.son_jpeg  = buf.tobytes()
                self.son_stats = {
                    "ogreniliyor":  False,
                    "kare":         self.kare_no,
                    "oran":         round(oran * 100, 1),
                    "ortalama":     round(ortalama * 100, 1),
                    "maksimum":     round(max(gecmis) * 100, 1) if gecmis else 0,
                    "etiket":       etiket,
                    "gecmis":       [round(x * 100, 1) for x in gecmis[-50:]],
                }

        cap.release()

    def son_kare(self):
        with self._lock:
            return self.son_jpeg

    def istatistik(self):
        with self._lock:
            return dict(self.son_stats)

    def durdur(self):
        self.aktif = False


def _trafik_worker_al(kaynak: str) -> TrafikWorker:
    if kaynak not in trafik_registry or not trafik_registry[kaynak].aktif:
        trafik_registry[kaynak] = TrafikWorker(kaynak)
    return trafik_registry[kaynak]


@app.get("/api/trafik-video-stream")
async def trafik_video_stream(kaynak: str = Query(...)):
    worker = _trafik_worker_al(kaynak)

    async def generate():
        while worker.aktif:
            jpeg = worker.son_kare()
            if jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + jpeg + b"\r\n")
            await asyncio.sleep(0.033)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.get("/api/trafik-istatistik-stream")
async def trafik_istatistik_stream(kaynak: str = Query(...)):
    worker = _trafik_worker_al(kaynak)

    async def generator():
        son_kare = -1
        while worker.aktif:
            stats = worker.istatistik()
            if stats and stats.get("kare", 0) != son_kare:
                son_kare = stats.get("kare", 0)
                yield f"data: {json.dumps(stats)}\n\n"
            await asyncio.sleep(0.1)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.delete("/api/trafik-stream-durdur")
async def trafik_stream_durdur(kaynak: str = Query(...)):
    if kaynak in trafik_registry:
        worker = trafik_registry[kaynak]
        stats  = worker.istatistik()
        if stats and not stats.get("ogreniliyor"):
            db.trafik_yogunluk_kaydet(
                kaynak   = kaynak,
                etiket   = stats.get("etiket", ""),
                oran     = float(stats.get("oran", 0)),
                ortalama = float(stats.get("ortalama", 0)),
                maksimum = float(stats.get("maksimum", 0)),
                kare     = int(stats.get("kare", 0))
            )
        worker.durdur()
        del trafik_registry[kaynak]
    return {"tamam": True}



# Uvicorn ile çalıştırmak için:
# C:\Users\EXCALIBUR\AppData\Local\spyder-6\envs\spyder-runtime\python.exe -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
