# 10_trafik_yogunluk.py
import cv2
import yt_dlp
import numpy as np
from collections import deque
import time

# Ayarlar:
ARKAPLAN_KARE_SAYISI = 30      # İlk N kare arka plan öğrenmek için kullanılır
DEGISIM_ESIGI  = 35      # 25'ten 35'e çıkar — küçük gürültüleri eله
YOGUN_ESIK     = 0.18    # 0.08'den 0.25'e — gerçekten yoğun olunca yoğun desin
NORMAL_ESIK    = 0.09    # 0.03'ten 0.12'ye
GECMIS_UZUNLUGU      = 150     # Grafik için kaç kare geçmişi tutulsun
GOSTER               = True
MAX_GENISLIK         = 960     # Performans için yeniden boyutlandır

# İlgilenilen bölge (ROI) — yolun olduğu alan
# (x_baslangic, y_baslangic, x_bitis, y_bitis) oransal (0.0-1.0)
# Kameraya göre ayarla; None = tüm görüntü
ROI = (0.05, 0.15, 0.95, 0.95)


def kaynak_coz(kaynak: str) -> str:
    k = kaynak.strip()
    if k.startswith("rtsp://") or k.startswith("rtsps://"):
        return k
    if k.endswith(".m3u8") or "m3u8" in k:
        return k
    # YouTube ve diğer tüm linkler
    try:
        print("  Link çözümleniyor (yt-dlp)...")
        ydl_opts = {
            "format": "best[height<=480][ext=mp4]/best[height<=480]/best",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(k, download=False)
            url  = info.get("url") or info["formats"][-1]["url"]
            print(f"  ✓ Çözümlendi: {url[:60]}...")
            return url
    except Exception as e:
        print(f"  [!] yt-dlp çözümleyemedi: {e}, direkt deneniyor...")
        return k


def yogunluk_etiketi(oran: float) -> tuple:
    """Oran → (etiket, renk) döner."""
    if oran >= YOGUN_ESIK:
        return "YOGUN",  (0, 0, 220)      # Kırmızı
    elif oran >= NORMAL_ESIK:
        return "NORMAL", (0, 165, 255)    # Turuncu
    else:
        return "SAKIN",  (0, 200, 80)     # Yeşil


def roi_kirp(kare: np.ndarray) -> tuple:
    """ROI bölgesini kırpar, koordinatları döner."""
    if ROI is None:
        return kare, 0, 0
    h, w = kare.shape[:2]
    x1 = int(ROI[0] * w)
    y1 = int(ROI[1] * h)
    x2 = int(ROI[2] * w)
    y2 = int(ROI[3] * h)
    return kare[y1:y2, x1:x2], x1, y1


def grafik_ciz(kare: np.ndarray, gecmis: deque, genislik: int, yukseklik: int):
    """Sağ alt köşeye mini yoğunluk grafiği çizer."""
    if len(gecmis) < 2:
        return

    gx, gy = genislik - 220, yukseklik - 80
    gh, gw  = 60, 210

    # Arka plan
    cv2.rectangle(kare, (gx - 5, gy - 15), (gx + gw, gy + gh + 5), (0, 0, 0), -1)
    cv2.putText(kare, "Yogunluk Gecmisi", (gx, gy - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)

    liste  = list(gecmis)
    maks   = max(liste) if max(liste) > 0 else 1
    adim_x = gw / max(len(liste) - 1, 1)

    for i in range(1, len(liste)):
        x1 = int(gx + (i - 1) * adim_x)
        x2 = int(gx + i       * adim_x)
        y1 = int(gy + gh - (liste[i - 1] / maks) * gh)
        y2 = int(gy + gh - (liste[i]     / maks) * gh)

        etiket, renk = yogunluk_etiketi(liste[i])
        cv2.line(kare, (x1, y1), (x2, y2), renk, 2)

    # Eşik çizgileri
    yogun_y  = int(gy + gh - (YOGUN_ESIK  / maks) * gh)
    normal_y = int(gy + gh - (NORMAL_ESIK / maks) * gh)
    cv2.line(kare, (gx, yogun_y),  (gx + gw, yogun_y),  (0, 0, 180),   1)
    cv2.line(kare, (gx, normal_y), (gx + gw, normal_y), (0, 130, 200), 1)


def trafik_analiz(kaynak: str):
    print("=" * 55)
    print("  🚦 TRAFİK YOĞUNLUK ANALİZİ BAŞLATILIYOR")
    print("=" * 55)

    stream_url = kaynak_coz(kaynak)
    print(f"  Kaynak: {stream_url[:60]}...")

    cap = cv2.VideoCapture(stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    if not cap.isOpened():
        print("HATA: Video açılamadı!")
        return

    fps       = cap.get(cv2.CAP_PROP_FPS) or 25
    genislik  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    yukseklik = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"  {genislik}x{yukseklik} @ {fps:.1f} FPS\n")

    arkaplan      = None       # Öğrenilen arka plan (gri, float32)
    kare_no       = 0
    gecmis        = deque(maxlen=GECMIS_UZUNLUGU)
    arkaplan_buf  = []         # İlk N kare biriktirilir

    print("─" * 55)
    print("  Arka plan öğreniliyor, lütfen bekleyin...")
    print("  Çalışıyor... Durdurmak için 'Q' tuşuna basın")
    print("─" * 55)

    while True:
        ret, kare = cap.read()
        if not ret:
            time.sleep(0.05)
            continue

        kare_no += 1

        # Yeniden boyutlandır
        h, w = kare.shape[:2]
        if w > MAX_GENISLIK:
            oran  = MAX_GENISLIK / w
            kare  = cv2.resize(kare, (MAX_GENISLIK, int(h * oran)),
                               interpolation=cv2.INTER_LINEAR)

        gri = cv2.cvtColor(kare, cv2.COLOR_BGR2GRAY)
        gri = cv2.GaussianBlur(gri, (5, 5), 0)    # Gürültüyü azalt

        # ROI al
        roi_gri, roi_x, roi_y = roi_kirp(gri)
        roi_kare_gri = roi_gri

        #Arka plan öğrenme:
        if len(arkaplan_buf) < ARKAPLAN_KARE_SAYISI:
            arkaplan_buf.append(roi_gri.astype(np.float32))
            # Ekranda ilerleme göster
            ilerleme = int((len(arkaplan_buf) / ARKAPLAN_KARE_SAYISI) * 100)
            kare_kopyasi = kare.copy()
            cv2.rectangle(kare_kopyasi, (20, 20), (400, 60), (0, 0, 0), -1)
            cv2.putText(kare_kopyasi,
                        f"Arka plan ogreniliyor... %{ilerleme}",
                        (30, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
            if GOSTER:
                cv2.imshow("Trafik Yogunluk - Q ile cik", kare_kopyasi)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            continue

        if arkaplan is None:
            arkaplan = np.mean(arkaplan_buf, axis=0).astype(np.float32)
            print("  ✓ Arka plan öğrenildi, analiz başlıyor...\n")

        #Fark hesapla:
        fark = cv2.absdiff(arkaplan, roi_gri.astype(np.float32))
        fark = fark.astype(np.uint8)

        # Eşikleme — sadece belirgin değişimleri say
        _, maske = cv2.threshold(fark, DEGISIM_ESIGI, 255, cv2.THRESH_BINARY)

        # Gürültü temizle
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        maske  = cv2.morphologyEx(maske, cv2.MORPH_OPEN,  kernel)
        maske  = cv2.morphologyEx(maske, cv2.MORPH_CLOSE, kernel)

        # Değişen piksel oranı
        toplam_piksel   = maske.size
        degisen_piksel  = np.count_nonzero(maske)
        oran            = degisen_piksel / toplam_piksel
        gecmis.append(oran)

        etiket, renk = yogunluk_etiketi(oran)

        # ROI dikdörtgenini ana kareye çiz:
        if ROI:
            h2, w2 = kare.shape[:2]
            rx1 = int(ROI[0] * w2); ry1 = int(ROI[1] * h2)
            rx2 = int(ROI[2] * w2); ry2 = int(ROI[3] * h2)
            cv2.rectangle(kare, (rx1, ry1), (rx2, ry2), renk, 2)

        # Sol üst bilgi paneli:
        panel_genislik = 260
        cv2.rectangle(kare, (5, 5), (panel_genislik, 90), (0, 0, 0), -1)

        cv2.putText(kare, etiket, (15, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, renk, 3)

        cv2.putText(kare, f"Degisim: %{oran * 100:.1f}", (15, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

        cv2.putText(kare, f"Kare: {kare_no}", (15, 82),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (140, 140, 140), 1)

        # Hareket maskesini sağ üste küçük göster:
        h2, w2 = kare.shape[:2]
        mask_kucuk = cv2.resize(maske, (160, 90))
        mask_renkli = cv2.cvtColor(mask_kucuk, cv2.COLOR_GRAY2BGR)
        kare[10:100, w2 - 170: w2 - 10] = mask_renkli
        cv2.putText(kare, "Hareket maskesi", (w2 - 168, 108),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)

        # Grafik:
        grafik_ciz(kare, gecmis, w2, h2)

        # Konsol özeti (her 50 karede bir)
        if kare_no % 50 == 0:
            print(f"  Kare {kare_no:5d} → {etiket:<6}  Değişim: %{oran*100:.1f}")

        if GOSTER:
            cv2.imshow("Trafik Yogunluk - Q ile cik", kare)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\n[!] Kullanıcı tarafından durduruldu.")
                break

    cap.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 55)
    print("  📊 ÖZET")
    print("=" * 55)
    if gecmis:
        ortalama = np.mean(list(gecmis)) * 100
        maksimum = np.max(list(gecmis))  * 100
        son_etiket, _ = yogunluk_etiketi(list(gecmis)[-1])
        print(f"  İşlenen kare   : {kare_no}")
        print(f"  Ort. değişim   : %{ortalama:.1f}")
        print(f"  Maks. değişim  : %{maksimum:.1f}")
        print(f"  Son durum      : {son_etiket}")
    print("=" * 55)


if __name__ == "__main__":
    kaynak = input("HLS (m3u8) veya RTSP URL girin: ").strip()
    trafik_analiz(kaynak)