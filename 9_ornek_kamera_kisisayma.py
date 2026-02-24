import cv2
import subprocess
import numpy as np
from ultralytics import YOLO
import time
from collections import deque

# YOLO modelini yükle (daha hızlı versiyon)
model = YOLO('yolov8n.pt')

hls_url = "https://content.tvkur.com/l/c77ia4vbb2nj4i0fr85g/master.m3u8"

# Daha düşük çözünürlük ve FPS ile FFmpeg başlat
ffmpeg_cmd = [
    'ffmpeg',
    '-headers', 'Referer: https://player.tvkur.com/\r\nx-referer: https://player.tvkur.com/\r\n',
    '-i', hls_url,
    '-f', 'image2pipe',
    '-pix_fmt', 'bgr24',
    '-vcodec', 'rawvideo',
    '-s', '426x240',  # Çözünürlüğü daha da düşür
    '-r', '10',  # 10 fps (daha akıcı)
    '-'
]

process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)

width, height = 426, 240
frame_size = width * height * 3

# Son 5 tespiti tut (dalgalanmayı azalt)
son_sayilar = deque(maxlen=5)

print("Canlı yayında kişi sayımı başladı...")
print("Çıkmak için 'q' tuşuna basın")

while True:
    raw_frame = process.stdout.read(frame_size)
    if len(raw_frame) != frame_size:
        print("🔄 Akış kesildi, yeniden bağlanılıyor...")
        process.terminate()
        time.sleep(1)
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**8)
        continue
        
    frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3))
    
    # YOLO ile tespit (verbose=False ile sessiz)
    results = model(frame, verbose=False)
    
    # Kişi sayısını bul
    person_count = 0
    for box in results[0].boxes:
        if int(box.cls[0]) == 0:  # person
            person_count += 1
    
    # Son sayıları kuyruğa ekle
    son_sayilar.append(person_count)
    kararli_sayi = int(sum(son_sayilar) / len(son_sayilar))
    
    # Sonucu göster
    annotated = results[0].plot()
    cv2.putText(annotated, f"Kisi: {kararli_sayi}", (10, 30), 
               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.putText(annotated, f"(anlik: {person_count})", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    
    cv2.imshow('YOLOv8 Kisi Sayaci', annotated)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

process.terminate()
cv2.destroyAllWindows()