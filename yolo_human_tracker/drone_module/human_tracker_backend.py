import cv2
import numpy as np
from ultralytics import YOLO
import torch
import os
import pickle
from collections import deque
import face_recognition

class HumanTrackerBackend:
    def __init__(self):
        # --- Device setup ---
        self.device = 'cpu'
        if torch.cuda.is_available():
            self.device = 'cuda'
        elif torch.backends.mps.is_available():
            self.device = 'mps'
        print(f"Using device for YOLO: {self.device}")

        self.yolo_model = YOLO('yolov8n.pt').to(self.device)

        # --- Face recognition config ---
        self.FACE_RECOGNITION_DISTANCE_THRESHOLD = 0.6
        self.MAX_FACE_IMAGES_PER_PERSON = 15
        self.MIN_DISTINCT_FACE_DISTANCE = 0.4

        # --- Persistence ---
        self.data_dir = os.path.join(os.path.expanduser("~"), ".yolo_human_tracker")
        os.makedirs(self.data_dir, exist_ok=True)
        self.KNOWN_FACES_DB_PATH = os.path.join(self.data_dir, "known_faces.pkl")

        # --- Tracking ---
        self.tracked_objects = {}
        self.next_person_id_counter = 0
        self.known_faces_db = {}

        self.load_known_faces()

        # --- State ---
        self.face_recognition_enabled = False
        self.low_light_enhancement_enabled = False

        # --- Stream State ---
        self.paused = False

        # --- Drawing ---
        self.BOX_COLORS = {
            "recognized": (0, 255, 0),
            "unidentified": (0, 165, 255),
            "unknown": (0, 0, 255),
            "face": (255, 0, 0)
        }
        self.FONT = cv2.FONT_HERSHEY_SIMPLEX
        self.FONT_SCALE = 0.6
        self.FONT_THICKNESS = 2

    # ---------------------- Persistence ----------------------
    def load_known_faces(self):
        if os.path.exists(self.KNOWN_FACES_DB_PATH):
            try:
                with open(self.KNOWN_FACES_DB_PATH, 'rb') as f:
                    data = pickle.load(f)
                    self.known_faces_db = data.get('known_faces_db', {})
                # Set next_person_id_counter
                max_id = -1
                for face_id in self.known_faces_db.keys():
                    if isinstance(face_id, str) and face_id.startswith("Unidentified_"):
                        try:
                            num = int(face_id.split("_")[1])
                            max_id = max(max_id, num)
                        except:
                            pass
                self.next_person_id_counter = max_id + 1
                # Ensure encodings are deque
                for face_id, data in self.known_faces_db.items():
                    if not isinstance(data['encodings'], deque):
                        data['encodings'] = deque(data['encodings'], maxlen=self.MAX_FACE_IMAGES_PER_PERSON)
                    if 'image' not in data: data['image'] = None
                    if 'name' not in data: data['name'] = 'Unknown'
                print(f"Loaded {len(self.known_faces_db)} known faces")
            except Exception as e:
                print(f"Error loading known faces: {e}")
                self.known_faces_db = {}
        else:
            print("No known faces found. Starting fresh.")

    def save_known_faces(self):
        try:
            with open(self.KNOWN_FACES_DB_PATH, 'wb') as f:
                pickle.dump({'known_faces_db': self.known_faces_db}, f)
            print(f"Saved {len(self.known_faces_db)} known faces")
        except Exception as e:
            print(f"Error saving known faces: {e}")

    def import_ibis_faces(self, users_data):
        print(f"Importing {len(users_data)} users from IBIS API.")
        for user_data in users_data:
            user_id = user_data.get("user_id")
            name = user_data.get("name")
            face_encoding = user_data.get("face_encoding")

            if user_id and name and isinstance(face_encoding, np.ndarray) and face_encoding.size > 0:
                if user_id not in self.known_faces_db:
                    self.known_faces_db[user_id] = {
                        'encodings': deque(maxlen=self.MAX_FACE_IMAGES_PER_PERSON),
                        'image': None,  # No image data directly from API for now
                        'name': name
                    }
                # Add the new encoding, ensuring uniqueness or recency if deque is full
                # For simplicity, we add directly. Deque's maxlen handles older ones.
                self.known_faces_db[user_id]['encodings'].append(face_encoding)
                print(f"Imported face for user: {name} ({user_id})")
            else:
                print(f"Skipping invalid user data during IBIS import: {user_data.get('user_id', 'N/A')}")

    # ---------------------- Feature toggles ----------------------
    def toggle_face_recognition(self):
        self.face_recognition_enabled = not self.face_recognition_enabled
        return self.face_recognition_enabled

    def toggle_low_light_enhancement(self):
        self.low_light_enhancement_enabled = not self.low_light_enhancement_enabled
        return self.low_light_enhancement_enabled

    # ---------------------- Frame processing ----------------------
    def process_frame(self, frame):
        if self.low_light_enhancement_enabled:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            cl = clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
            frame = cv2.bilateralFilter(frame, 9, 75, 75)

        # YOLO detection
        results = self.yolo_model(frame, device=self.device, verbose=False)
        detections = []
        for r in results:
            for box in r.boxes:
                if self.yolo_model.names[int(box.cls)] == 'person':
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])
                    detections.append([x1, y1, x2, y2, conf])

        centroids = [(int((x1+x2)/2), int((y1+y2)/2)) for x1,y1,x2,y2,_ in detections]

        # Prepare known face encodings
        known_encodings = []
        known_ids = []
        for face_id, data in self.known_faces_db.items():
            for enc in data['encodings']:
                if isinstance(enc, np.ndarray) and enc.size > 0:
                    known_encodings.append(enc)
                    known_ids.append(face_id)

        # --- Track objects ---
        next_tracked = {}
        used = set()
        for pid, obj in self.tracked_objects.items():
            min_dist = float('inf')
            best_idx = -1
            for i, c in enumerate(centroids):
                if i in used: continue
                dist = np.linalg.norm(np.array(obj['centroid']) - np.array(c))
                if dist < 150 and dist < min_dist:
                    min_dist = dist
                    best_idx = i
            if best_idx != -1:
                det = detections[best_idx]
                next_tracked[pid] = {**obj, 'box': det[:4], 'centroid': centroids[best_idx]}
                used.add(best_idx)

        # Add new detections
        for i, det in enumerate(detections):
            if i in used: continue
            pid = f"person_{self.next_person_id_counter}"
            self.next_person_id_counter += 1
            next_tracked[pid] = {'box': det[:4], 'centroid': centroids[i], 'face_id': None, 'face_rect': None, 'face_confidence': 0.0, 'name':'Unknown'}

        # --- Face recognition ---
        for pid, obj in next_tracked.items():
            if self.face_recognition_enabled and (obj['face_id'] is None or obj['face_id'] == "No Face Detected"):
                x1, y1, x2, y2 = obj['box']
                x1, y1, x2, y2 = max(0, x1), max(0, y1), min(frame.shape[1], x2), min(frame.shape[0], y2)
                roi = frame[y1:y2, x1:x2]
                if roi.size == 0: continue
                rgb_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                faces = face_recognition.face_locations(rgb_roi)
                if faces:
                    face_rect = faces[0]
                    obj['face_rect'] = face_rect
                    enc_list = face_recognition.face_encodings(rgb_roi, [face_rect])
                    if enc_list:
                        encoding = enc_list[0]
                        match_found = False
                        if known_encodings:
                            distances = face_recognition.face_distance(known_encodings, encoding)
                            best_idx = np.argmin(distances)
                            if distances[best_idx] < self.FACE_RECOGNITION_DISTANCE_THRESHOLD:
                                fid = known_ids[best_idx]
                                obj.update({
                                    'face_id': fid,
                                    'name': self.known_faces_db[fid].get('name', 'Unknown'),
                                    'face_confidence': 1.0 - distances[best_idx]
                                })
                                match_found = True
                        if not match_found:
                            fid = f"Unidentified_{self.next_person_id_counter}"
                            self.next_person_id_counter +=1
                            top, right, bottom, left = face_rect
                            face_img = roi[top:bottom, left:right]
                            self.known_faces_db[fid] = {
                                'encodings': deque([encoding], maxlen=self.MAX_FACE_IMAGES_PER_PERSON),
                                'image': cv2.resize(face_img,(100,100)) if face_img.size>0 else None,
                                'name':'Unknown'
                            }
                            obj['face_id'] = fid
                    else:
                        obj['face_id'] = "No Face Detected"
                else:
                    obj['face_id'] = "No Face Detected"

        self.tracked_objects = next_tracked
        frame = self.draw_overlays(frame, self.tracked_objects)
        return frame, self.tracked_objects, self.known_faces_db

    # ---------------------- Drawing ----------------------
    def draw_overlays(self, frame, tracked_objects):
        for pid, obj in tracked_objects.items():
            x1, y1, x2, y2 = obj['box']
            name = obj.get('name', 'Unknown')
            color = self.BOX_COLORS['recognized'] if name != 'Unknown' else self.BOX_COLORS['unidentified']
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, name, (x1, y1-10), self.FONT, self.FONT_SCALE, color, self.FONT_THICKNESS)
            # Draw face rectangle
            if obj.get('face_rect'):
                top, right, bottom, left = obj['face_rect']
                top += y1; bottom += y1; left += x1; right += x1
                cv2.rectangle(frame, (left, top), (right, bottom), self.BOX_COLORS['face'], 1)
        return frame
