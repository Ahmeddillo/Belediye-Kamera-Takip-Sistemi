# 6_havadurumu_tespiti_img.py
import cv2
import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
import sys

# Ayarlar:
# -----------------------------------------------
# Test etmek istediğin fotoğrafın adını yaz
FOTOGRAF_YOLU = "w-test2 .png" 

# CLIP için etiket sözlüğü (İngilizce Tanım: Türkçe Karşılık)
etiket_sozlugu = {
    "clear sunny weather with bright sky": "☀️ Gunesli",
    "partly cloudy sky with some sun": "⛅ Parcali Bulutlu",
    "overcast cloudy and grey sky": "☁️ Bulutlu / Kapali",
    "rainy weather with wet ground and puddles": "🌧️ Yagmurlu / Islak",
    "snowy winter or thick foggy weather": "❄️ Karli / Sisli",
    "dark night time street view": "🌙 Gece / Karanlik",
    "blurry vision or dirty camera lens obstruction": "⚠️ Gorus Kisitli / Kirli Lens"
}

ingilizce_etiketler = list(etiket_sozlugu.keys())
# -----------------------------------------------

print("🔄 CLIP Modeli yükleniyor...")
model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
print("✅ Model hazır!\n")

def resmi_analiz_et(resim_yolu):
    # OpenCV ile resmi oku
    frame = cv2.imread(resim_yolu)
    
    if frame is None:
        print(f"❌ HATA: '{resim_yolu}' bulunamadı.")
        sys.exit()

    # BGR -> RGB çevrimi
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_image = Image.fromarray(rgb_frame)

    print(f"🔍 '{resim_yolu}' analiz ediliyor...")
    
    # Modele gönder
    inputs = processor(text=ingilizce_etiketler, images=pil_image, return_tensors="pt", padding=True)
    
    with torch.no_grad():
        outputs = model(**inputs)
    
    # Softmax ile yüzdelik hesapla
    logits_per_image = outputs.logits_per_image
    ihtimaller = logits_per_image.softmax(dim=1).cpu().numpy()[0]
    
    # Terminale detaylı dağılımı yazdır
    print("\n📊 --- MODELİN KARAR DAĞILIMI ---")
    for i, oran in enumerate(ihtimaller):
        tr_karsiligi = etiket_sozlugu[ingilizce_etiketler[i]]
        # Görsel düzen için ljust kullanıldı
        print(f"{tr_karsiligi.ljust(35)} : %{oran * 100:.2f}")
    print("--------------------------------\n")
    
    # En yüksek ihtimali bul
    en_yuksek_index = ihtimaller.argmax()
    secilen_ingilizce = ingilizce_etiketler[en_yuksek_index]
    tahmin_tr = etiket_sozlugu[secilen_ingilizce]
    gosterilecek_oran = ihtimaller[en_yuksek_index] * 100
    
    # Ekrana yazdırma hazırlığı
    gosterim_kopyasi = frame.copy()
    cv2.rectangle(gosterim_kopyasi, (10, 10), (600, 70), (0, 0, 0), -1)
    
    # OpenCV'de emoji desteği olmadığı için emojiyi terminalde bırakıp 
    # ekrana metin kısmını yazıyoruz
    saf_metin = tahmin_tr.split(" ", 1)[-1] # Emojiyi ayıkla
    ekran_metni = f"Durum: {saf_metin} (%{gosterilecek_oran:.1f})"
    
    cv2.putText(gosterim_kopyasi, ekran_metni, (20, 50), 
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    
    cv2.imshow("Hava Durumu ve Kamera Durumu Tespiti", gosterim_kopyasi)
    print("💡 Kapatmak için bir tuşa basın.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    resmi_analiz_et(FOTOGRAF_YOLU)
