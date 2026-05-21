import urllib.request
import os

print("Downloading YuNet Face Detection model...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_detection_yunet.onnx"
)
print("Downloading SFace Recognition model...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    "face_recognition_sface.onnx"
)
print("Downloads complete.")
