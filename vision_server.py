import cv2
import threading
import time
import sqlite3
import re
import os
from datetime import datetime
from collections import Counter
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from ultralytics import YOLO
import easyocr
import numpy as np
import pandas as pd
from db_security import encrypt_data, encrypt_bytes # Import the new helper


app = FastAPI()
DB_NAME = 'alpr_data.db'

# ── Asset directories ─────────────────────────────────────────────────
MODELS_DIR = os.path.join("assets", "Models")
VIDEOS_DIR = os.path.join("assets", "videos")

def _init_db():
    """Ensure all required tables exist before the server starts processing."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS movements
            (id INTEGER PRIMARY KEY AUTOINCREMENT, vehicle_id INTEGER, event TEXT,
             timestamp DATETIME, plate TEXT, snapshot_path TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist
            (plate TEXT PRIMARY KEY, reason TEXT, added_on DATETIME)''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS vehicle_profiles (
                plate               TEXT PRIMARY KEY,
                first_seen          DATETIME,
                last_seen           DATETIME,
                total_visits        INTEGER DEFAULT 0,
                total_entries       INTEGER DEFAULT 0,
                total_exits         INTEGER DEFAULT 0,
                notes               TEXT DEFAULT '',
                last_snapshot_path  TEXT DEFAULT ''
            )
        ''')
        conn.execute('''CREATE TABLE IF NOT EXISTS face_movements
            (id INTEGER PRIMARY KEY AUTOINCREMENT, face_id INTEGER, event TEXT,
             timestamp DATETIME, name TEXT, snapshot_path TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS face_watchlist
            (name TEXT PRIMARY KEY, reason TEXT, added_on DATETIME)''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS face_profiles (
                name                TEXT PRIMARY KEY,
                embedding           BLOB,
                first_seen          DATETIME,
                last_seen           DATETIME,
                total_visits        INTEGER DEFAULT 0,
                notes               TEXT DEFAULT '',
                last_snapshot_path  TEXT DEFAULT '',
                face_id             INTEGER
            )
        ''')
        # Add face_id column if it doesn't exist yet (migration for existing DBs)
        try:
            conn.execute("ALTER TABLE face_profiles ADD COLUMN face_id INTEGER")
        except sqlite3.OperationalError:
            pass  # Column already exists
        # Back-fill face_id from rowid for any profiles that lack one
        conn.execute(
            "UPDATE face_profiles SET face_id = rowid WHERE face_id IS NULL"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_face_profiles_face_id "
            "ON face_profiles(face_id)"
        )
        conn.commit()

_init_db()

class CameraProcessor:
    def __init__(self, name, source, coco_model, plate_model, reader, parent):
        self.name = name
        self.source = source
        self.coco_model = coco_model
        self.plate_model = plate_model
        self.reader = reader
        self.parent = parent
        self.cap = cv2.VideoCapture(source)
        self.latest_frame = None
        self.plate_history = {}
        self.prev_positions = {}
        self.lock = threading.Lock()
        self.trigger_line_y = 600
        threading.Thread(target=self._run_inference, daemon=True).start()

    def _run_inference(self):
        frame_count = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                if isinstance(self.source, str) and self.source.endswith(('.mp4', '.avi', '.mov')):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            frame_count += 1
            if frame_count % 4 != 0:
                continue

            # 1. VEHICLE TRACKING
            with self.parent.model_lock:
                v_res = self.coco_model.track(frame, persist=True, tracker="bytetrack.yaml", verbose=False, conf=0.4)[0]
            vehicle_dict = {}
            
            if v_res.boxes.id is not None:
                for box, tid, cls in zip(v_res.boxes.xyxy.cpu().numpy(), v_res.boxes.id.cpu().numpy().astype(int), v_res.boxes.cls.cpu().numpy().astype(int)):
                    if cls in [2, 3, 5, 7]:
                        vehicle_dict[tid] = box
                        cv2.rectangle(frame, (int(box[0]), int(box[1])), (int(box[2]), int(box[3])), (0, 255, 0), 2)
                        
                        cy = (box[1] + box[3]) / 2
                        if tid in self.prev_positions:
                            py = self.prev_positions[tid]
                            # Simple line crossing trigger - Direction is dictated by self.name
                            if (py < self.trigger_line_y and cy >= self.trigger_line_y) or (py > self.trigger_line_y and cy <= self.trigger_line_y):
                                best_plate = Counter(self.plate_history.get(tid, ["UNKNOWN"])).most_common(1)[0][0]
                                
                                # SAVE ENCRYPTED COMPRESSED SNAPSHOT
                                snap_path = self.parent._get_snapshot_path(best_plate, tid)
                                
                                # 1. Downscale slightly if frame is large (max 1280px width)
                                h, w = frame.shape[:2]
                                if w > 1280:
                                    scale = 1280 / w
                                    save_frame = cv2.resize(frame, (0,0), fx=scale, fy=scale)
                                else:
                                    save_frame = frame

                                # 2. Encode with reduced JPEG quality (50% for high compression)
                                success, buffer = cv2.imencode('.jpg', save_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                                
                                if success:
                                    encrypted_img = encrypt_bytes(buffer.tobytes())
                                    with open(snap_path, 'wb') as f:
                                        f.write(encrypted_img)
                                 
                                self.parent._save_to_db(tid, self.name, best_plate, snap_path)
                                
                                if best_plate in self.parent.watchlist:
                                    with self.parent.lock:
                                        self.parent.alert_queue.append({"plate": best_plate, "time": datetime.now().strftime("%H:%M:%S"), "event": self.name})
                        self.prev_positions[tid] = cy

            # 2. PLATE DETECTION & OCR
            with self.parent.model_lock:
                lp_res = self.plate_model(frame, verbose=False, conf=0.3)[0]
            for lp in lp_res.boxes.data.tolist():
                lx1, ly1, lx2, ly2, _, _ = lp
                cv2.rectangle(frame, (int(lx1), int(ly1)), (int(lx2), int(ly2)), (255, 0, 0), 2)
                
                for cid, cbox in vehicle_dict.items():
                    if cbox[0] < lx1 < cbox[2] and cbox[1] < ly1 < cbox[3]:
                        lp_crop = frame[int(ly1):int(ly2), int(lx1):int(lx2)]
                        if lp_crop.size > 0:
                            lp_resz = cv2.resize(cv2.cvtColor(lp_crop, cv2.COLOR_BGR2GRAY), None, fx=2, fy=2)
                            with self.parent.model_lock:
                                ocr_res = self.reader.readtext(lp_resz)
                            if ocr_res:
                                txt = re.sub(r'[^A-Z0-9]', '', ocr_res[0][1].upper())
                                if len(txt) >= 5:
                                    if cid not in self.plate_history: self.plate_history[cid] = []
                                    self.plate_history[cid].append(txt)

            # 3. DRAW OCR TEXT & TRIGGER LINE
            for cid, plates in self.plate_history.items():
                if cid in vehicle_dict:
                    box = vehicle_dict[cid]
                    best = Counter(plates).most_common(1)[0][0]
                    cv2.putText(frame, f"ID:{cid} {best}", (int(box[0]), int(box[1])-10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            cv2.line(frame, (0, self.trigger_line_y), (frame.shape[1], self.trigger_line_y), (0, 0, 255), 3)
            cv2.putText(frame, f"{self.name} GATE", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
            
            with self.lock:
                _, buffer = cv2.imencode('.jpg', frame)
                self.latest_frame = buffer.tobytes()
            time.sleep(0.01)

class FaceProcessor:
    def __init__(self, name, source, detector, recognizer, parent):
        self.name = name
        self.source = source
        self.detector = detector
        self.recognizer = recognizer
        self.parent = parent
        self.cap = cv2.VideoCapture(source)
        self.latest_frame = None
        self.lock = threading.Lock()
        threading.Thread(target=self._run_inference, daemon=True).start()

    def _run_inference(self):
        frame_count = 0
        while True:
            ret, frame = self.cap.read()
            if not ret:
                if isinstance(self.source, str) and self.source.endswith(('.mp4', '.avi', '.mov')):
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                break

            frame_count += 1
            if frame_count % 5 != 0:
                continue

            h, w = frame.shape[:2]
            with self.parent.model_lock:
                self.detector.setInputSize((w, h))
                _, faces = self.detector.detect(frame)

            if faces is not None:
                for face in faces:
                    box = list(map(int, face[:4]))
                    # Validate box bounds
                    if box[0] < 0 or box[1] < 0 or box[0]+box[2] > w or box[1]+box[3] > h:
                        continue

                    with self.parent.model_lock:
                        face_align = self.recognizer.alignCrop(frame, face)
                        face_feature = self.recognizer.feature(face_align)

                    best_match = "UNKNOWN"
                    best_score = 0.0
                    for name, known_feature in self.parent.face_profiles.items():
                        score = self.recognizer.match(face_feature, known_feature, cv2.FaceRecognizerSF_FR_COSINE)
                        if score >= 0.363 and score > best_score:
                            best_match = name
                            best_score = score

                    color = (0, 255, 0) if best_match != "UNKNOWN" else (0, 0, 255)
                    cv2.rectangle(frame, (box[0], box[1]), (box[0]+box[2], box[1]+box[3]), color, 2)
                    cv2.putText(frame, best_match, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

                    now = datetime.now()
                    if best_match not in self.parent.recent_face_detections or (now - self.parent.recent_face_detections[best_match]).seconds > 10:
                        snap_path = self.parent._get_face_snapshot_path(best_match)
                        if w > 1280:
                            scale = 1280 / w
                            save_frame = cv2.resize(frame, (0,0), fx=scale, fy=scale)
                        else:
                            save_frame = frame
                        
                        success, buffer = cv2.imencode('.jpg', save_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                        if success:
                            encrypted_img = encrypt_bytes(buffer.tobytes())
                            with open(snap_path, 'wb') as f:
                                f.write(encrypted_img)
                        self.parent._save_face_to_db(self.name, best_match, snap_path)
                        self.parent.recent_face_detections[best_match] = now
                        
                        if best_match in self.parent.face_watchlist:
                            with self.parent.lock:
                                self.parent.face_alert_queue.append({"name": best_match, "time": now.strftime("%H:%M:%S"), "event": self.name})

            with self.lock:
                _, buffer = cv2.imencode('.jpg', frame)
                self.latest_frame = buffer.tobytes()
            time.sleep(0.01)

class GlobalAIWorker:
    def __init__(self):
        # Shared Models
        self.reader = easyocr.Reader(['en'], gpu=True)
        self.coco_model = YOLO(os.path.join(MODELS_DIR, 'yolov8n.pt'))
        self.plate_model = YOLO(os.path.join(MODELS_DIR, 'license_plate_detector.pt'))
        
        self.alert_queue = []
        self.lock = threading.Lock()
        self.model_lock = threading.Lock()
        self.refresh_watchlist()
        
        # Initialize Dual Cameras (Using the same video as a placeholder if separate sources aren't available)
        self.entry_processor = CameraProcessor("ENTRY", os.path.join(VIDEOS_DIR, "license_plate_video.mp4"), self.coco_model, self.plate_model, self.reader, self)
        self.exit_processor  = CameraProcessor("EXIT",  os.path.join(VIDEOS_DIR, "license_plate_video.mp4"), self.coco_model, self.plate_model, self.reader, self)

        # Face Recognition
        try:
            self.face_detector  = cv2.FaceDetectorYN.create(
                os.path.join(MODELS_DIR, "face_detection_yunet.onnx"), "", (320, 320)
            )
            self.face_recognizer = cv2.FaceRecognizerSF.create(
                os.path.join(MODELS_DIR, "face_recognition_sface.onnx"), ""
            )
        except Exception as e:
            print("Could not load face models:", e)
            self.face_detector, self.face_recognizer = None, None
            
        self.face_alert_queue = []
        self.recent_face_detections = {}
        self.face_profiles = {}
        self.face_watchlist = set()
        self.refresh_face_profiles()
        self.refresh_face_watchlist()
        if self.face_detector and self.face_recognizer:
            self.face_processor = FaceProcessor(
                "MAIN_ENTRY", os.path.join(VIDEOS_DIR, "face_video.mp4"),
                self.face_detector, self.face_recognizer, self
            )

    def refresh_watchlist(self):
        with sqlite3.connect(DB_NAME) as conn:
            try:
                self.watchlist = set(pd.read_sql_query("SELECT plate FROM watchlist", conn)['plate'].tolist())
            except: self.watchlist = set()

    def refresh_face_watchlist(self):
        with sqlite3.connect(DB_NAME) as conn:
            try:
                self.face_watchlist = set(pd.read_sql_query("SELECT name FROM face_watchlist", conn)['name'].tolist())
            except: self.face_watchlist = set()

    def refresh_face_profiles(self):
        with sqlite3.connect(DB_NAME) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, embedding FROM face_profiles WHERE embedding IS NOT NULL")
            rows = cursor.fetchall()
            self.face_profiles = {}
            for row in rows:
                name, blob = row
                feature = np.frombuffer(blob, dtype=np.float32).reshape(1, 128)
                self.face_profiles[name] = feature

    def _get_face_snapshot_path(self, name):
        now = datetime.now()
        folder = os.path.join("snapshots", "faces", now.strftime("%Y"), now.strftime("%B-%Y"), now.strftime("%d-%m-%Y"))
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"{now.strftime('%H%M%S')}_{name}.jpg")

    def _save_face_to_db(self, event, name, snap_path):
        secure_name = encrypt_data(name)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_NAME) as conn:
            face_id = 0  # Default for UNKNOWN
            if name != "UNKNOWN":
                conn.execute('''
                    INSERT INTO face_profiles (name, first_seen, last_seen, total_visits, last_snapshot_path)
                    VALUES (:name, :now, :now, 1, :snap)
                    ON CONFLICT(name) DO UPDATE SET
                        last_seen         = :now,
                        total_visits      = total_visits + 1,
                        last_snapshot_path = :snap
                ''', {
                    "name": name,
                    "now":   now_str,
                    "snap":  snap_path
                })
                # Ensure face_id is set (back-fill on first detection if missing)
                conn.execute(
                    "UPDATE face_profiles SET face_id = rowid "
                    "WHERE name = ? AND face_id IS NULL",
                    (name,)
                )
                row = conn.execute(
                    "SELECT face_id FROM face_profiles WHERE name = ?",
                    (name,)
                ).fetchone()
                if row:
                    face_id = row[0]
            conn.execute(
                "INSERT INTO face_movements (face_id, event, timestamp, name, snapshot_path) "
                "VALUES (?,?,?,?,?)",
                (face_id, event, now_str, secure_name, snap_path)
            )

    def _get_snapshot_path(self, plate, tid):
        now = datetime.now()
        year = now.strftime("%Y")
        month_year = now.strftime("%B-%Y")
        day_month_year = now.strftime("%d-%m-%Y")
        
        folder = os.path.join("snapshots", year, month_year, day_month_year)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
            
        filename = f"{now.strftime('%H%M%S')}_ID{tid}_{plate}.jpg"
        return os.path.join(folder, filename)

    def _save_to_db(self, tid, event, plate, snap_path):
        secure_plate = encrypt_data(plate)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(DB_NAME) as conn:
            # 1. Log raw movement (unchanged)
            conn.execute(
                "INSERT INTO movements (vehicle_id, event, timestamp, plate, snapshot_path) VALUES (?,?,?,?,?)",
                (tid, event, now_str, secure_plate, snap_path)
            )

            # 2. Upsert the vehicle profile (keyed on plain plate text)
            conn.execute('''
                INSERT INTO vehicle_profiles (plate, first_seen, last_seen, total_visits,
                                             total_entries, total_exits, last_snapshot_path)
                VALUES (:plate, :now, :now, 1,
                        :is_entry, :is_exit, :snap)
                ON CONFLICT(plate) DO UPDATE SET
                    last_seen         = :now,
                    total_visits      = total_visits + 1,
                    total_entries     = total_entries + :is_entry,
                    total_exits       = total_exits  + :is_exit,
                    last_snapshot_path = :snap
            ''', {
                "plate": plate,
                "now":   now_str,
                "is_entry": 1 if event == "ENTRY" else 0,
                "is_exit":  1 if event == "EXIT"  else 0,
                "snap":  snap_path
            })

worker = GlobalAIWorker()

@app.get("/video_entry")
async def video_entry():
    def frame_generator():
        while True:
            if worker.entry_processor.latest_frame:
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + worker.entry_processor.latest_frame + b'\r\n')
            time.sleep(0.03)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/video_exit")
async def video_exit():
    def frame_generator():
        while True:
            if worker.exit_processor.latest_frame:
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + worker.exit_processor.latest_frame + b'\r\n')
            time.sleep(0.03)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/alerts")
async def get_alerts():
    with worker.lock:
        alerts = list(worker.alert_queue)
        worker.alert_queue.clear()
    return {"alerts": alerts}

@app.get("/video_face")
async def video_face():
    def frame_generator():
        while True:
            if hasattr(worker, 'face_processor') and worker.face_processor.latest_frame:
                yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + worker.face_processor.latest_frame + b'\r\n')
            time.sleep(0.03)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/face_alerts")
async def get_face_alerts():
    with worker.lock:
        alerts = list(worker.face_alert_queue)
        worker.face_alert_queue.clear()
    return {"alerts": alerts}

@app.post("/refresh_face_profiles")
async def api_refresh_face_profiles():
    with worker.model_lock:
        worker.refresh_face_profiles()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)