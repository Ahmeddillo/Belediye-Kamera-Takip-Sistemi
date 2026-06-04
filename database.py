# database.py
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime
import time

class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.pool = None
        self.max_retry = 3
        self.retry_delay = 2
        
    def connect(self):
        for i in range(self.max_retry):
            try:
                self.pool = SimpleConnectionPool(
                    minconn=1,
                    maxconn=10,
                    **self.config
                )
                print("✅ PostgreSQL bağlantı havuzu oluşturuldu")
                self.create_tables()
                return True
            except Exception as e:
                print(f"⚠️ Bağlantı hatası ({i+1}/{self.max_retry}): {e}")
                time.sleep(self.retry_delay)
        return False
    
    def get_connection(self):
        if not self.pool:
            if not self.connect():
                raise Exception("PostgreSQL bağlantısı kurulamadı")
        return self.pool.getconn()
    
    def return_connection(self, conn):
        if self.pool and conn:
            self.pool.putconn(conn)

    def create_tables(self):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kameralar (
                        id SERIAL PRIMARY KEY,
                        ad VARCHAR(255) NOT NULL,
                        konum VARCHAR(255),
                        rtsp_url VARCHAR(500),
                        aktif BOOLEAN DEFAULT true,
                        olusturma_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS dakikalik_olculer (
                        id SERIAL PRIMARY KEY,
                        kamera_id INTEGER REFERENCES kameralar(id),
                        baslangic_zamani TIMESTAMP,
                        bitis_zamani TIMESTAMP,
                        toplam_kisi INTEGER,
                        ortalama_kisi FLOAT,
                        maksimum_kisi INTEGER,
                        minimum_kisi INTEGER,
                        fps_ortalamasi FLOAT,
                        detaylar JSONB,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS anlik_olcumler (
                        id SERIAL PRIMARY KEY,
                        kamera_id INTEGER REFERENCES kameralar(id),
                        kisi_sayisi INTEGER,
                        olcum_zamani TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hava_durumu (
                        id SERIAL PRIMARY KEY,
                        kamera_id INTEGER REFERENCES kameralar(id),
                        durum VARCHAR(255),
                        guven_orani FLOAT,
                        tespit_zamani TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS arac_sayim_kayitlari (
                        id              SERIAL PRIMARY KEY,
                        tarih           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        kaynak          VARCHAR(500),
                        toplam_arac     INTEGER,
                        sinif_sayimlari JSONB,
                        islenen_kare    INTEGER
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS trafik_yogunluk_kayitlari (
                        id              SERIAL PRIMARY KEY,
                        tarih           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        kaynak          VARCHAR(500),
                        etiket          VARCHAR(20),
                        degisim_orani   NUMERIC(5,2),
                        ortalama        NUMERIC(5,2),
                        maksimum        NUMERIC(5,2),
                        islenen_kare    INTEGER
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS plaka_kayitlari (
                        id              SERIAL PRIMARY KEY,
                        tarih           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        ham_metin       VARCHAR(20),
                        duzeltilmis     VARCHAR(20),
                        formatli_plaka  VARCHAR(20),
                        gecerli_mi      BOOLEAN,
                        guven_tespit    NUMERIC(4,2),
                        guven_ocr       NUMERIC(4,2),
                        dosya_adi       VARCHAR(255)
                    )
                """)
                conn.commit()
                print("✅ Veritabanı tabloları oluşturuldu")
        except Exception as e:
            print(f"⚠️ Tablo oluşturma hatası: {e}")
            conn.rollback()
        finally:
            self.return_connection(conn)

    def dakikalik_kaydet(self, kamera_id, baslangic, bitis, toplam_kisi, 
                         ortalama, maksimum, minimum, fps, detaylar=None):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dakikalik_olculer 
                    (kamera_id, baslangic_zamani, bitis_zamani, toplam_kisi, 
                     ortalama_kisi, maksimum_kisi, minimum_kisi, fps_ortalamasi, detaylar)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    kamera_id, baslangic, bitis, toplam_kisi, ortalama,
                    maksimum, minimum, fps, Json(detaylar) if detaylar else None
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"❌ Kayıt hatası: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
    
    def anlik_kaydet(self, kamera_id, kisi_sayisi):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO anlik_olcumler (kamera_id, kisi_sayisi)
                    VALUES (%s, %s)
                """, (kamera_id, kisi_sayisi))
                conn.commit()
        finally:
            self.return_connection(conn)
    
    def son_dakika_verisi(self, kamera_id):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM dakikalik_olculer 
                    WHERE kamera_id = %s 
                    ORDER BY baslangic_zamani DESC 
                    LIMIT 1
                """, (kamera_id,))
                return cur.fetchone()
        finally:
            self.return_connection(conn)
    
    def saatlik_rapor(self, kamera_id, tarih=None):
        if not tarih:
            tarih = datetime.now().date()
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        date_trunc('hour', baslangic_zamani) as saat,
                        COUNT(*) as dakika_sayisi,
                        SUM(toplam_kisi) as saatlik_toplam,
                        AVG(ortalama_kisi) as ortalama_kisi,
                        MAX(maksimum_kisi) as en_kalabalik
                    FROM dakikalik_olculer 
                    WHERE kamera_id = %s 
                        AND baslangic_zamani::date = %s::date
                    GROUP BY saat
                    ORDER BY saat
                """, (kamera_id, tarih))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
    
    def gunluk_rapor(self, kamera_id, baslangic, bitis):
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        baslangic_zamani::date as gun,
                        COUNT(*) as olcum_sayisi,
                        SUM(toplam_kisi) as gunluk_toplam,
                        AVG(ortalama_kisi) as gunluk_ortalama
                    FROM dakikalik_olculer 
                    WHERE kamera_id = %s 
                        AND baslangic_zamani::date BETWEEN %s::date AND %s::date
                    GROUP BY gun
                    ORDER BY gun
                """, (kamera_id, baslangic, bitis))
                return cur.fetchall()
        finally:
            self.return_connection(conn)
            
    def hava_durumu_kaydet(self, kamera_id, durum, guven_orani):
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Son kayıttan bu yana 30 saniye geçti mi kontrol et
                cur.execute("""
                    SELECT tespit_zamani FROM hava_durumu
                    WHERE kamera_id = %s
                    ORDER BY tespit_zamani DESC
                    LIMIT 1
                """, (kamera_id,))
                son_kayit = cur.fetchone()
    
                if son_kayit:
                    gecen_sure = (datetime.now() - son_kayit[0]).total_seconds()
                    if gecen_sure < 30:
                        return False  # 30 saniye dolmadı, yazma
    
                cur.execute("""
                    INSERT INTO hava_durumu (kamera_id, durum, guven_orani)
                    VALUES (%s, %s, %s)
                """, (kamera_id, durum, guven_orani))
                conn.commit()
                return True
    
        except Exception as e:
            print(f"❌ Hava durumu kayıt hatası: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)
 
    def hava_durumu_gecmis(self, kamera_id, tarih=None):
        if not tarih:
            tarih = datetime.now().date()
        conn = self.get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT durum, guven_orani, tespit_zamani
                    FROM hava_durumu
                    WHERE kamera_id = %s
                        AND tespit_zamani::date = %s::date
                    ORDER BY tespit_zamani ASC
                """, (kamera_id, tarih))
                return cur.fetchall()
        finally:
            self.return_connection(conn)

    def arac_sayim_kaydet(self, kaynak: str, toplam: int,
                          sinif_sayimlari: dict, islenen_kare: int) -> bool:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO arac_sayim_kayitlari
                        (kaynak, toplam_arac, sinif_sayimlari, islenen_kare)
                    VALUES (%s, %s, %s, %s)
                """, (kaynak[:500], toplam, Json(sinif_sayimlari), islenen_kare))
                conn.commit()
                print(f"✅ Araç sayımı kaydedildi: {toplam} araç, {islenen_kare} kare")
                return True
        except Exception as e:
            print(f"❌ Araç sayımı kayıt hatası: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def trafik_yogunluk_kaydet(self, kaynak: str, etiket: str, oran: float,
                                ortalama: float, maksimum: float, kare: int) -> bool:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trafik_yogunluk_kayitlari
                        (kaynak, etiket, degisim_orani, ortalama, maksimum, islenen_kare)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (kaynak[:500], etiket, oran, ortalama, maksimum, kare))
                conn.commit()
                print(f"✅ Trafik yoğunluk kaydedildi: {etiket}, %{oran}")
                return True
        except Exception as e:
            print(f"❌ Trafik kayıt hatası: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def plaka_kaydet(self, ham: str, duzeltilmis: str, formatli: str,
                     gecerli: bool, guven_tespit: float, guven_ocr: float,
                     dosya_adi: str = "") -> bool:
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO plaka_kayitlari
                        (ham_metin, duzeltilmis, formatli_plaka, gecerli_mi,
                         guven_tespit, guven_ocr, dosya_adi)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (ham, duzeltilmis, formatli, gecerli,
                      guven_tespit, guven_ocr, dosya_adi))
                conn.commit()
                print(f"✅ Plaka kaydedildi: {formatli} ({'✓' if gecerli else '✗'})")
                return True
        except Exception as e:
            print(f"❌ Plaka kayıt hatası: {e}")
            conn.rollback()
            return False
        finally:
            self.return_connection(conn)

    def close(self):
        if self.pool:
            self.pool.closeall()
            print("🔒 PostgreSQL bağlantıları kapatıldı")
