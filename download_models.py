import urllib.request
import os

MODELS_DIR = os.path.join("assets", "Models")
os.makedirs(MODELS_DIR, exist_ok=True)

print("Downloading YuNet Face Detection model...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    os.path.join(MODELS_DIR, "face_detection_yunet.onnx")
)
print("Downloading SFace Recognition model...")
urllib.request.urlretrieve(
    "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
    os.path.join(MODELS_DIR, "face_recognition_sface.onnx")
)
print(f"Downloads complete — models saved to: {MODELS_DIR}")
