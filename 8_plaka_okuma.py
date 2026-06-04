# 8_plaka_okuma.py

import cv2
import numpy as np
from ultralytics import YOLO
import json
import os
import re
from datetime import datetime
from pathlib import Path

class TurkishPlateSystem:
    def __init__(self, detector_path, ocr_path):
        # 2.2 - Modelleri Yükle
        print("🔄 Modeller yükleniyor...")
        self.detector = YOLO(detector_path).to('cpu')
        self.ocr_model = YOLO(ocr_path).to('cpu')
        
        # Türkiye İl Kodları
        self.PROVINCES = [str(i).zfill(2) for i in range(1, 82)]
        
    def pre_process(self, image):
        """2.1 - Görüntü Ön-İşleme (Pre-processing)"""
        if image is None or image.size == 0:
            return None
    
        border = 20
        image = cv2.copyMakeBorder(image, border, border, border, border, 
                                   cv2.BORDER_CONSTANT, value=[0, 0, 0])
        # gri tonlamaya dönüştürme:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # aşağıda clahe uygulanmıştır
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        contrast = clahe.apply(gray)
        # Görüntüyü keskinleştirmek için unsharp masking
        denoised = cv2.bilateralFilter(contrast, 11, 75, 75)
    
        gaussian = cv2.GaussianBlur(denoised, (5, 5), 1.0)
        unsharp = cv2.addWeighted(denoised, 2.0, gaussian, -1.0, 0)
        # Eşikleme (Thresholding)
        thresh = cv2.adaptiveThreshold(unsharp, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)
        # Morfolojik İşlemler (Gürültü temizleme)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel)
    
        final_image = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)
        return final_image

    def correct_ocr_errors(self, text):
        """2.4 - AKILLI OCR DÜZELTME"""
        text = text.upper().replace(" ", "").strip()
        
        match = re.match(r'^(\d{2})([A-Z0-9]{1,3})(\d{2,4})$', text)
        
        if match:
            prov, letters, nums = match.groups()
            
            letter_corr = {'5': 'S', '0': 'O', '1': 'I', '8': 'B'}
            for wrong, right in letter_corr.items():
                letters = letters.replace(wrong, right)
                
            num_corr = {'S': '5', 'O': '0', 'I': '1', 'B': '8', 'L': '1'}
            for wrong, right in num_corr.items():
                nums = nums.replace(wrong, right)
                
            return f"{prov}{letters}{nums}"
        
        basic_corr = {'|': 'I', 'L': 'I'}
        for w, r in basic_corr.items():
            text = text.replace(w, r)
        return text

    def validate_plate(self, text):
        """2.4 - Türk Plaka Format Kontrolü"""
        clean_text = re.sub(r'[^A-Z0-9]', '', text)
        
        pattern = r'^(\d{2})([A-Z]{1,3})(\d{2,4})$'
        match = re.match(pattern, clean_text)
        
        if not match:
            return False, clean_text
            
        prov, letters, nums = match.groups()
        
        if prov not in self.PROVINCES:
            return False, clean_text
            
        forbidden = {'İ', 'Ş', 'Ç', 'Ğ', 'Ü', 'Ö', 'Q', 'W', 'X'}
        if any(f in letters for f in forbidden):
            return False, clean_text
            
        return True, f"{prov} {letters} {nums}"

    def process_folder(self, folder_path, output_folder="results"):
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
            
        if not os.path.exists(folder_path):
            print(f"❌ Hata: {folder_path} klasörü bulunamadı!")
            return

        image_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
        images = [f for f in os.listdir(folder_path) if f.lower().endswith(image_extensions)]
        
        final_results = []

        for img_name in images:
            img_path = os.path.join(folder_path, img_name)
            img = cv2.imread(img_path)
            if img is None: 
                continue

            detect_results = self.detector(img, verbose=False)
            
            for res in detect_results:
                for box in res.boxes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf_detect = float(box.conf[0])
                    
                    # Crop'u genişlet
                    width = x2 - x1
                    height = y2 - y1
                    
                    x1 = max(0, x1 - int(width * 0.3))
                    x2 = min(img.shape[1], x2 + int(width * 0.3))
                    y1 = max(0, y1 - int(height * 0.1))
                    y2 = min(img.shape[0], y2 + int(height * 0.1))
                    
                    plate_crop = img[y1:y2, x1:x2]
                    processed_plate = self.pre_process(plate_crop)
                    if processed_plate is None: 
                        continue
                    
                    ocr_res = self.ocr_model(processed_plate, verbose=False)
                    
                    # Karakterleri x koordinatına göre sırala
                    boxes = ocr_res[0].boxes.data.tolist()
                    boxes.sort(key=lambda x: x[0])
                    
                    raw_text = ""
                    for b in boxes:
                        class_id = int(b[5])
                        char = self.ocr_model.names[class_id]
                        raw_text += char
                    
                    conf_ocr = np.mean([b[4] for b in boxes]) if boxes else 0
                    
                    # Düzeltme adımı
                    corrected_text = self.correct_ocr_errors(raw_text)
                    is_valid, formatted_plate = self.validate_plate(corrected_text)
                    
                    output = {
                        "timestamp": datetime.now().isoformat(),
                        "filename": img_name,
                        "raw_text": raw_text,
                        "corrected_text": corrected_text,
                        "formatted_plate": formatted_plate,
                        "is_valid": is_valid,
                        "confidence": {
                            "detection": round(conf_detect, 2),
                            "ocr": round(float(conf_ocr), 2)
                        }
                    }
                    final_results.append(output)
                    status = "✅" if is_valid else "⚠️"
                    print(f"{status} İşlendi: {img_name} -> {formatted_plate} (Ham: {raw_text})")

        json_output = os.path.join(output_folder, "plaka_sonuclari.json")
        with open(json_output, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)
        print(f"\n📂 İşlem tamamlandı. Sonuçlar: {json_output}")

if __name__ == "__main__":
    DETECTOR_PATH = "plaka_bulma.pt"
    OCR_PATH = "plaka_okuma.pt"
    TEST_FOLDER = "test_resimleri"
    
    try:
        app = TurkishPlateSystem(DETECTOR_PATH, OCR_PATH)
        app.process_folder(TEST_FOLDER)
    except Exception as e:
        print(f"❌ Kritik Hata: {e}")