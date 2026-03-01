# database_test.py
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from datetime import datetime
import time

print("=" * 50)
print("📦 PostgreSQL Veritabanı Bağlantı Testi")
print("=" * 50)

# Konfigürasyon
PG_CONFIG = {
    'host': 'localhost',
    'database': 'belediye_kamera_db',
    'user': 'postgres',
    'password': 'Hello',
    'port': 5432
}

print(f"🔌 Bağlanıyor: {PG_CONFIG['host']}/{PG_CONFIG['database']}")

try:
    # Direkt bağlantı dene
    conn = psycopg2.connect(**PG_CONFIG)
    print("✅ Veritabanına başarıyla bağlandı!")
    
    # Tabloları kontrol et
    with conn.cursor() as cur:
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tablolar = cur.fetchall()
        
        if tablolar:
            print(f"📋 Bulunan tablolar:")
            for tablo in tablolar:
                print(f"   - {tablo[0]}")
        else:
            print("⚠️ Henüz tablo oluşturulmamış.")
    
    conn.close()
    print("🔒 Bağlantı kapatıldı.")
    
except Exception as e:
    print(f"❌ HATA: {e}")
    print("\n💡 ÇÖZÜM ÖNERİLERİ:")
    print("1. PostgreSQL servisi çalışıyor mu?")
    print("2. 'belediye_kamera_db' veritabanı oluşturuldu mu?")
    print("3. Kullanıcı adı/şifre doğru mu? (postgres/sifre)")
    print("4. Port 5432 açık mı?")

print("=" * 50)