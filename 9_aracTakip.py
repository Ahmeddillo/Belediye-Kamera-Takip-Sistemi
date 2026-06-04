# 9_aracTakip.py
import cv2
import yt_dlp
from ultralytics import YOLO
from collections import defaultdict

# Ayarlar:
MODEL_YOLU  = "arac2.pt"
GUVEN_ESI   = 0.4
GOSTER      = True
KAYDET      = False
CIKTI_DOSYA = "sonuc.mp4"
MAX_KARE    = 0          # 0 = süresiz (RTSP için önerilir)



def kaynak_coz(kaynak: str) -> str:
    """RTSP URL'sini olduğu gibi, YouTube'u yt-dlp ile çözerek döner."""
    k = kaynak.strip()
    if k.startswith("rtsp://") or k.startswith("rtsps://"):
        print("      RTSP kaynağı algılandı, doğrudan açılıyor.")
        return k
    if "youtube" in k.lower() or "youtu.be" in k.lower():
        print("      YouTube linki algılandı, stream URL çözümleniyor...")
        ydl_opts = {"format": "best[ext=mp4]/best", "quiet": True, "no_warnings": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(k, download=False)
            return info["url"]
    # Diğer (HTTP stream, yerel dosya vb.)
    return k


def arac_say(kaynak: str):
    print("=" * 55)
    print("  🚗 ARAÇ SAYICI BAŞLATILIYOR")
    print("=" * 55)

    print(f"[1/3] Model yükleniyor: {MODEL_YOLU}")
    model  = YOLO(MODEL_YOLU)
    siniflar = model.names
    print(f"      Sınıflar: {list(siniflar.values())}")

    print(f"[2/3] Kaynak çözümleniyor...")
    stream_url = kaynak_coz(kaynak)
    print("      ✓ Kaynak hazır")

    print(f"[3/3] Video açılıyor...")
    cap = cv2.VideoCapture(stream_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # RTSP gecikmesini azaltır
    if not cap.isOpened():
        print("HATA: Video/RTSP akışı açılamadı!")
        return

    fps      = cap.get(cv2.CAP_PROP_FPS) or 25
    genislik = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    yukseklik = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"      ✓ {genislik}x{yukseklik} @ {fps:.1f} FPS\n")

    yazici = None
    if KAYDET:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        yazici = cv2.VideoWriter(CIKTI_DOSYA, fourcc, fps, (genislik, yukseklik))
        print(f"Kayıt açıldı: {CIKTI_DOSYA}")

    renkler = [
        (0, 120, 255), (0, 210, 100), (255, 80, 0),
        (180, 0, 255), (0, 220, 220), (255, 200, 0),
    ]

    kare_no        = 0
    en_yuksek_kare = defaultdict(int)

    print("─" * 55)
    print("  Çalışıyor... Durdurmak için 'Q' tuşuna basın")
    print("─" * 55)

    while True:
        ret, kare = cap.read()
        if not ret:
            # RTSP'de geçici kopma olabilir — kısa bekle, yeniden dene
            print("[!] Kare okunamadı, yeniden deneniyor...")
            cv2.waitKey(500)
            continue

        kare_no += 1
        if MAX_KARE > 0 and kare_no > MAX_KARE:
            print(f"\n[✓] Maksimum kare ({MAX_KARE}) doldu, durduruluyor.")
            break

        sonuclar = model(kare, conf=GUVEN_ESI, verbose=False)[0]
        kare_sayimlari = defaultdict(int)

        for kutu in sonuclar.boxes:
            cls_id   = int(kutu.cls[0])
            cls_adi  = siniflar[cls_id]
            guven    = float(kutu.conf[0])
            x1, y1, x2, y2 = map(int, kutu.xyxy[0])

            kare_sayimlari[cls_adi] += 1

            renk = renkler[cls_id % len(renkler)]
            cv2.rectangle(kare, (x1, y1), (x2, y2), renk, 2)

            etiket = f"{cls_adi} {guven:.0%}"
            (tw, th), _ = cv2.getTextSize(etiket, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
            cv2.rectangle(kare, (x1, y1 - th - 8), (x1 + tw + 6, y1), renk, -1)
            cv2.putText(kare, etiket, (x1 + 3, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        for cls, sayi in kare_sayimlari.items():
            if sayi > en_yuksek_kare[cls]:
                en_yuksek_kare[cls] = sayi

        # Sol üst panel
        toplam = sum(kare_sayimlari.values())
        satirlar = [f"Toplam: {toplam}"] + \
                   [f"  {k}: {v}" for k, v in sorted(kare_sayimlari.items())]
        panel_h = 18 + 20 * len(satirlar)
        cv2.rectangle(kare, (5, 5), (200, panel_h), (0, 0, 0), -1)
        for i, s in enumerate(satirlar):
            cv2.putText(kare, s, (10, 22 + i * 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        # Sağ alt: kare no
        cv2.putText(kare, f"#{kare_no}", (genislik - 80, yukseklik - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1)

        if KAYDET and yazici:
            yazici.write(kare)

        if GOSTER:
            cv2.imshow("Arac Sayici - Q ile cik", kare)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("\n[!] Kullanıcı tarafından durduruldu.")
                break

        if kare_no % 100 == 0:
            ozet = " | ".join(f"{k}:{v}" for k, v in kare_sayimlari.items())
            print(f"  Kare {kare_no:5d} → {ozet if ozet else 'araç yok'}")

    cap.release()
    if yazici:
        yazici.release()
    cv2.destroyAllWindows()

    print("\n" + "=" * 55)
    print("  📊 RAPOR")
    print("=" * 55)
    print(f"  İşlenen kare: {kare_no}")
    print(f"\n  Tek karede en yüksek eş zamanlı sayılar:")
    if en_yuksek_kare:
        for cls, sayi in sorted(en_yuksek_kare.items(), key=lambda x: -x[1]):
            print(f"    🔹 {cls:<15} : {sayi}")
    else:
        print("    Hiç araç tespit edilmedi.")
    print("=" * 55)


if __name__ == "__main__":
    kaynak = input("RTSP veya YouTube URL girin: ").strip()
    arac_say(kaynak)