# api.py
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
            "/son-dakika/{kamera_id}",
            "/saatlik-rapor/{kamera_id}",
            "/gunluk-rapor/{kamera_id}",
            "/canli/{kamera_id}",
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
            "durum_ozeti": ozet,         # {"Gunesli": 4, "Bulutlu": 2} gibi
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

# Uvicorn ile çalıştırmak için:
# python -m uvicorn api:app --reload --host 0.0.0.0 --port 8000