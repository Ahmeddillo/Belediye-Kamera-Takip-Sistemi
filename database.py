# database.py
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime
import time

class DatabaseManager:
    def __init__(self, config):
        """
        PostgreSQL bağlantı yöneticisi
        config: {
            'host': 'localhost',
            'database': 'belediye_kamera_db',
            'user': 'postgres',
            'password': 'Hello',
            'port': 5432
        }
        """
        self.config = config
        self.pool = None
        self.max_retry = 3
        self.retry_delay = 2
        
    def connect(self):
        """Bağlantı havuzunu oluştur"""
        for i in range(self.max_retry):
            try:
                self.pool = SimpleConnectionPool(
                    minconn=1,
                    maxconn=10,
                    **self.config
                )
                print("✅ PostgreSQL bağlantı havuzu oluşturuldu")
                return True
            except Exception as e:
                print(f"⚠️ Bağlantı hatası ({i+1}/{self.max_retry}): {e}")
                time.sleep(self.retry_delay)
        return False
    
    def get_connection(self):
        """Havuzdan bağlantı al"""
        if not self.pool:
            if not self.connect():
                raise Exception("PostgreSQL bağlantısı kurulamadı")
        return self.pool.getconn()
    
    def return_connection(self, conn):
        """Bağlantıyı havuza geri ver"""
        if self.pool and conn:
            self.pool.putconn(conn)
    
    def dakikalik_kaydet(self, kamera_id, baslangic, bitis, toplam_kisi, 
                         ortalama, maksimum, minimum, fps, detaylar=None):
        """Dakikalık veriyi kaydet"""
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
        """Anlık veriyi kaydet (10 saniyede bir)"""
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
        """Son dakika verisini getir"""
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
        """Saatlik rapor getir"""
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
            
            
    def hava_durumu_kaydet(self, kamera_id, durum, guven_orani):
        """
        Hava durumunu kaydet — sadece önceki kayıttan farklıysa yazar.
        Aynı durum tekrar tekrar DB'ye yazılmaz.
        
        Parametreler:
            kamera_id  : int   — hangi kameraya ait
            durum      : str   — Türkçe etiket ("Gunesli", "Yagmurlu" vb.)
            guven_orani: float — CLIP'in yüzdelik güven skoru (ör: 87.3)
        
        Döndürür:
            True  → yeni kayıt yazıldı (durum değişmişti)
            False → yazılmadı (durum aynıydı) veya hata
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Son kaydedilen durumu kontrol et
                cur.execute("""
                    SELECT durum FROM hava_durumu
                    WHERE kamera_id = %s
                    ORDER BY tespit_zamani DESC
                    LIMIT 1
                """, (kamera_id,))
                son_kayit = cur.fetchone()
 
                # Aynı durumsa yazma
                if son_kayit and son_kayit[0] == durum:
                    return False
 
                # Farklıysa yaz
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
        """
        Belirli bir güne ait hava durumu geçmişini getirir.
        tarih verilmezse bugün kullanılır.
        """
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
    
    def close(self):
        """Tüm bağlantıları kapat"""
        if self.pool:
            self.pool.closeall()
            print("🔒 PostgreSQL bağlantıları kapatıldı")