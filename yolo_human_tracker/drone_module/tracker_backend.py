import cv2
import numpy as np
from ultralytics import YOLO
import torch
import os
import pickle
from collections import deque
import face_recognition
from ultralytics.trackers.utils.gmc import GMC
import math

class HumanTrackerBackend:
    def __init__(self):
        # --- Device setup ---
        self.device = 'cpu'
        if torch.cuda.is_available():
            self.device = 'cuda'
        elif torch.backends.mps.is_available():
            self.device = 'mps'
        print(f"Using device for YOLO: {self.device}")

        self.yolo_model_path = 'yolov9c.pt'
        self.tensorrt_engine_path = 'yolov9c.engine'

        # Attempt to load TensorRT engine first for maximum performance on NVIDIA GPUs
        if self.device == 'cuda' and os.path.exists(self.tensorrt_engine_path):
            try:
                print(f"Attempting to load TensorRT engine: {self.tensorrt_engine_path}")
                self.yolo_model = YOLO(self.tensorrt_engine_path).to(self.device)
                print("TensorRT engine loaded successfully.")
            except Exception as e:
                print(f"Failed to load TensorRT engine: {e}. Falling back to PyTorch model.")
                self.yolo_model = YOLO(self.yolo_model_path).to(self.device)
        else:
            # Fallback to PyTorch model if TensorRT not applicable or engine not found
            self.yolo_model = YOLO(self.yolo_model_path).to(self.device)
        
        # --- TensorRT Export and Compilation (Instructions for User) ---
        # If you have an NVIDIA GPU and TensorRT installed, you can compile the .pt model
        # to a TensorRT engine for optimal performance.
        # Steps:
        # 1. Ensure you have the 'yolov9c.pt' model file in the project root.
        # 2. Run the following command in a Python environment with ultralytics, torch, and tensorrt installed:
        #    from ultralytics import YOLO
        #    model = YOLO('yolov9c.pt')
        #    model.export(format='engine', device=0, imgsz=640, half=True, workspace=4)
        #    (Adjust device, imgsz, half, workspace as needed. imgsz is usually square, e.g., 640 or 1280)
        #    This will generate 'yolov9c.engine' in the project root.
        # 3. Place 'yolov9c.engine' in the project root alongside 'yolov9c.pt'.
        # 4. The system will then automatically attempt to load the .engine file if 'cuda' device is available.
        # ------------------------------------------------------------------

        # Initialize GMC (Global Motion Compensation)
        self.gmc_tracker = GMC(method="sparseOptFlow")

        # --- YuNet Face Detector ---
        self.YUNET_MODEL_PATH = 'models/face_detection_yunet_2023mar.onnx'
        try:
            self.yunet_detector = cv2.FaceDetectorYN.create(self.YUNET_MODEL_PATH, "", (320, 320))
            if self.yunet_detector is not None:
                # Set preferable backend and target for M2 chip optimization
                # self.yunet_detector.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV) # Not an attribute of FaceDetectorYN
                # self.yunet_detector.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU) # Not an attribute of FaceDetectorYN
                print("YuNet ONNX model loaded successfully using cv2.FaceDetectorYN.")
                # For potential MPS acceleration (if supported by OpenCV's DNN for ONNX)
                if torch.backends.mps.is_available():
                    print("MPS (Metal Performance Shaders) is available. Consider trying DNN_TARGET_MPS if issues arise with CPU.")
            else:
                raise Exception("Failed to create cv2.FaceDetectorYN object.")
        except Exception as e:
            print(f"Error loading YuNet ONNX model: {e}. Face detection will not be available.")
            self.yunet_detector = None

        # --- RetinaFace Model ---



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
        self.selected_person_id = None # New attribute for selected person
        
        # --- Face Recognition Performance Optimization ---
        self.frame_count = 0
        self.face_recognition_interval = 10  # Process face recognition every N frames
        self.last_face_recognition_frame = 0
        self.face_cache = {}  # Cache face encodings temporarily
        self.cache_expiry = 30  # Cache expires after N frames

        # --- Stream State ---
        self.paused = False

        # --- Drawing ---
        self.BOX_COLORS = {
            "recognized": (0, 255, 0),
            "unidentified": (0, 165, 255),
            "unknown": (0, 0, 255),
            "face": (255, 0, 0) # Changed from face as an explicit request by the user
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

    def set_selected_person(self, person_id):
        self.selected_person_id = person_id
        print(f"Selected person: {self.selected_person_id}")



    def get_tracked_object_info(self, person_id):
        """
        Returns the tracking information for a given person_id.
        """
        return self.tracked_objects.get(person_id)

    def get_current_unidentified_faces_for_saving(self):
        """
        Returns a list of currently tracked but unidentified faces,
        suitable for presenting to the user for saving and identification.
        """
        unidentified_faces_info = []
        for face_id, data in self.known_faces_db.items():
            if face_id.startswith("Unidentified_"):
                face_image = data.get('image')
                face_encoding = data.get('encodings')[0] if data.get('encodings') else None
                
                if face_image is not None and face_encoding is not None:
                    unidentified_faces_info.append({
                        'person_id': face_id, # Use the Unidentified_X as the person_id for saving
                        'face_image': face_image,
                        'face_encoding': face_encoding
                    })
        return unidentified_faces_info

    def save_new_face(self, encoding, name):
        """
        Saves a new identified face to the known faces database.
        Args:
            encoding (np.ndarray): The face encoding to save.
            name (str): The name associated with this face.
        Returns:
            tuple: (success (bool), message (str))
        """
        try:
            # Check if name already exists as an ID in known_faces_db
            if name in self.known_faces_db:
                # If name exists, add this new encoding to the existing entry
                self.known_faces_db[name]['encodings'].append(encoding)
                message = f"Added new encoding for existing person: {name}."
            else:
                # Create a new entry for this person
                self.known_faces_db[name] = {
                    'encodings': deque([encoding], maxlen=self.MAX_FACE_IMAGES_PER_PERSON),
                    'image': None, # No image provided directly in this method
                    'name': name
                }
                message = f"New person '{name}' saved successfully."

            self.save_known_faces() # Save the updated database to disk
            return True, message
        except Exception as e:
            return False, f"Error saving new face: {e}"

    def get_unidentified_face_ids(self):
        """
        Returns a list of IDs for currently unidentified faces in the database.
        """
        return [face_id for face_id in self.known_faces_db.keys() if face_id.startswith("Unidentified_")]

    def name_unidentified_person(self, target_face_id, new_name):
        """
        Assigns a new name to an unidentified face and updates the database.
        Args:
            target_face_id (str): The 'Unidentified_' ID of the face to name.
            new_name (str): The new name for this face.
        Returns:
            tuple: (success (bool), message (str))
        """
        try:
            if target_face_id not in self.known_faces_db or not target_face_id.startswith("Unidentified_"):
                return False, "Target face ID not found or is already identified."

            if new_name in self.known_faces_db:
                # Merge encodings if new_name already exists
                existing_data = self.known_faces_db[new_name]
                new_face_data = self.known_faces_db[target_face_id]
                
                # Append new encodings, respecting maxlen
                for enc in new_face_data['encodings']:
                    if enc not in existing_data['encodings']: # Avoid duplicates if possible
                        existing_data['encodings'].append(enc)
                message = f"Merged '{target_face_id}' into existing person '{new_name}'."
            else:
                # Rename the entry in known_faces_db
                self.known_faces_db[new_name] = self.known_faces_db[target_face_id]
                self.known_faces_db[new_name]['name'] = new_name # Update the name field
                message = f"Unidentified face '{target_face_id}' named as '{new_name}'."

            del self.known_faces_db[target_face_id] # Remove the old unidentified entry
            self.save_known_faces()
            return True, message
        except Exception as e:
            return False, f"Error naming unidentified person: {e}"

    def get_known_person_names(self):
        """
        Returns a list of names for identified people in the database (not starting with "Unidentified_").
        """
        return [name for name in self.known_faces_db.keys() if not name.startswith("Unidentified_")]

    def edit_person_name(self, old_name, new_name):
        """
        Edits the name of an identified person in the database.
        Args:
            old_name (str): The current name of the person.
            new_name (str): The new name for the person.
        Returns:
            tuple: (success (bool), message (str))
        """
        try:
            if old_name not in self.known_faces_db:
                return False, f"Person '{old_name}' not found in the database."
            if new_name == old_name:
                return False, "New name is the same as the old name."
            if new_name.startswith("Unidentified_"):
                return False, "Cannot rename to an 'Unidentified_' ID format."

            if new_name in self.known_faces_db:
                # Merge encodings if new_name already exists
                existing_data = self.known_faces_db[new_name]
                old_name_data = self.known_faces_db[old_name]
                
                for enc in old_name_data['encodings']:
                    if enc not in existing_data['encodings']:
                        existing_data['encodings'].append(enc)
                message = f"Merged '{old_name}' into existing person '{new_name}'."
            else:
                # Rename the entry
                self.known_faces_db[new_name] = self.known_faces_db[old_name]
                self.known_faces_db[new_name]['name'] = new_name
                message = f"Person '{old_name}' renamed to '{new_name}'."

            del self.known_faces_db[old_name] # Remove the old entry
            self.save_known_faces()
            return True, message
        except Exception as e:
            return False, f"Error editing person's name: {e}"



    # ---------------------- Frame processing ----------------------
    def process_frame(self, frame):
        if self.paused:
            return frame, self.tracked_objects, self.known_faces_db

        if self.low_light_enhancement_enabled:
            lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            cl = clahe.apply(l)
            frame = cv2.cvtColor(cv2.merge((cl, a, b)), cv2.COLOR_LAB2BGR)
            frame = cv2.bilateralFilter(frame, 9, 75, 75)

        # Perform tracking using YOLOv8's track method with the custom ByteTrack config
        # The 'tracker' argument points to our custom YAML file
        results = self.yolo_model.track(
            source=frame,
            persist=True, # Persist tracks across frames
            device=self.device,
            verbose=False,
            tracker='drone_module/bytetrack_custom.yaml',
            conf=0.3, # Detection confidence threshold before tracking
            iou=0.5 # IoU threshold for NMS before tracking
        )

        # Process tracking results
        if results[0].boxes is not None and results[0].boxes.id is not None:
            # results[0].boxes.data contains [x1, y1, x2, y2, track_id, confidence, class_id]
            tracked_data = results[0].boxes.data.cpu().numpy()
            
            # Filter for 'person' class (class_id 0 in COCO, assuming yolov8 was trained on COCO)
            person_detections = tracked_data[tracked_data[:, -1] == 0] 

            current_tracked_objects = {}
            for *xyxy, track_id, conf, cls_id in person_detections:
                track_id = int(track_id)
                x1, y1, x2, y2 = map(int, xyxy)
                centroid = (int((x1 + x2) / 2), int((y1 + y2) / 2))

                obj = self.tracked_objects.get(track_id, {
                    'face_id': None, 
                    'face_rect': None, 
                    'face_confidence': 0.0, 
                    'name':'Unknown'
                })
                obj.update({
                    'box': [x1, y1, x2, y2],
                    'centroid': centroid,
                    'conf': float(conf),
                    'cls': int(cls_id)
                })
                current_tracked_objects[track_id] = obj
            self.tracked_objects = current_tracked_objects
        else:
            self.tracked_objects = {} # Clear tracked objects if nothing is detected/tracked

        # --- Face recognition for selected person using YuNet (OPTIMIZED) ---
        self.frame_count += 1
        
        # Only process face recognition every N frames for performance
        if (self.face_recognition_enabled and 
            self.yunet_detector is not None and 
            self.selected_person_id in self.tracked_objects and
            (self.frame_count - self.last_face_recognition_frame) >= self.face_recognition_interval):
            
            self.last_face_recognition_frame = self.frame_count
            obj = self.tracked_objects[self.selected_person_id]
            
            # Check if we have cached face data for this track_id
            if (self.selected_person_id in self.face_cache and 
                (self.frame_count - self.face_cache[self.selected_person_id]['frame']) < self.cache_expiry):
                # Use cached face data
                cached_data = self.face_cache[self.selected_person_id]
                obj.update({
                    'face_id': cached_data['face_id'],
                    'name': cached_data['name'], 
                    'face_confidence': cached_data.get('face_confidence', 0.0),
                    'face_rect': cached_data.get('face_rect')
                })
            else:
                # Process face recognition (expensive operation)
                self._process_face_recognition(obj, frame)
            x1, y1, x2, y2 = obj['box']
            # Ensure coordinates are within frame bounds
            x1, y1, x2, y2 = max(0, x1), max(0, y1), min(frame.shape[1], x2), min(frame.shape[0], y2)
            
            # Crop ROI for the selected person
            roi = frame[y1:y2, x1:x2]
            
            if roi.size > 0:
                h_roi, w_roi, _ = roi.shape
                
                # Calculate padding to make ROI square
                pad_left, pad_top = 0, 0
                if h_roi > w_roi:
                    pad_size = (h_roi - w_roi) // 2
                    padded_roi = cv2.copyMakeBorder(roi, 0, 0, pad_size, pad_size, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                    pad_left = pad_size
                elif w_roi > h_roi:
                    pad_size = (w_roi - h_roi) // 2
                    padded_roi = cv2.copyMakeBorder(roi, pad_size, pad_size, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                    pad_top = pad_size
                else: # Already square
                    padded_roi = roi
                
                # Resize padded ROI to the fixed input size of YuNet model
                resized_roi = cv2.resize(padded_roi, (320, 320))
                
                # Detect faces in the ROI using YuNet
                retval, faces_in_roi = self.yunet_detector.detect(resized_roi)
                
                # print(f"Type of faces_in_roi: {type(faces_in_roi)}, Value: {faces_in_roi}") # Debug statement removed after verification
                
                if retval and faces_in_roi is not None and len(faces_in_roi) > 0:
                    # Take the first detected face (assuming one main face per person bounding box)
                    # YuNet output: [x1, y1, w, h, score, ...]
                    x1_det, y1_det, w_det, h_det = map(int, faces_in_roi[0][:4])

                    # Scale factor from 320x320 to padded_roi size
                    scale_factor = padded_roi.shape[0] / 320 # Since padded_roi is square, width == height

                    # Adjust face_rect_roi coordinates back to the padded ROI scale
                    x1_scaled = int(x1_det * scale_factor)
                    y1_scaled = int(y1_det * scale_factor)
                    w_scaled = int(w_det * scale_factor)
                    h_scaled = int(h_det * scale_factor)

                    # Un-pad to get coordinates relative to the original 'roi'
                    x1_unpadded = x1_scaled - pad_left
                    y1_unpadded = y1_scaled - pad_top
                    
                    # Calculate corresponding bottom-right
                    x2_unpadded = x1_unpadded + w_scaled
                    y2_unpadded = y1_unpadded + h_scaled

                    # Convert to (top, right, bottom, left) format relative to original 'roi'
                    face_rect_roi_unpadded = (y1_unpadded, x2_unpadded, y2_unpadded, x1_unpadded)
                    
                    # Convert face_rect_roi_unpadded coordinates to original frame coordinates
                    top_orig = face_rect_roi_unpadded[0] + y1
                    right_orig = face_rect_roi_unpadded[1] + x1
                    bottom_orig = face_rect_roi_unpadded[2] + y1
                    left_orig = face_rect_roi_unpadded[3] + x1
                    face_rect_original_frame = (top_orig, right_orig, bottom_orig, left_orig)
                    
                    obj['face_rect'] = face_rect_original_frame # Store face rect in original frame coordinates

                    rgb_frame_for_encoding = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    enc_list = face_recognition.face_encodings(rgb_frame_for_encoding, [face_rect_original_frame])
                    
                    if enc_list:
                        encoding = enc_list[0]
                        match_found = False
                        if self.known_faces_db: # Only try matching if we have known faces
                            known_encodings_flat = []
                            known_ids_flat = []
                            for face_id, data in self.known_faces_db.items():
                                for enc in data['encodings']:
                                    known_encodings_flat.append(enc)
                                    known_ids_flat.append(face_id)
                            
                            if known_encodings_flat:
                                distances = face_recognition.face_distance(known_encodings_flat, encoding)
                                best_idx = np.argmin(distances)
                                if distances[best_idx] < self.FACE_RECOGNITION_DISTANCE_THRESHOLD:
                                    fid = known_ids_flat[best_idx]
                                    obj.update({
                                        'face_id': fid,
                                        'name': self.known_faces_db[fid].get('name', 'Unknown'),
                                        'face_confidence': 1.0 - distances[best_idx]
                                    })
                                    # Add new encoding to the deque for continuous learning if not too close
                                    if distances[best_idx] > self.MIN_DISTINCT_FACE_DISTANCE:
                                        self.known_faces_db[fid]['encodings'].append(encoding)
                                    match_found = True
                        if not match_found:
                            # Assign new "Unidentified" ID if no match is found
                            new_unidentified_id = f"Unidentified_{self.next_person_id_counter}"
                            self.next_person_id_counter += 1
                            
                            # Extract face image from original frame using corrected coordinates
                            face_img = frame[top_orig:bottom_orig, left_orig:right_orig]
                            self.known_faces_db[new_unidentified_id] = {
                                'encodings': deque([encoding], maxlen=self.MAX_FACE_IMAGES_PER_PERSON),
                                'image': cv2.resize(face_img, (100, 100)) if face_img.size > 0 else None,
                                'name': 'Unknown'
                            }
        frame = self.draw_overlays(frame, self.tracked_objects)
        return frame, self.tracked_objects, self.known_faces_db
    
    def _process_face_recognition(self, obj, frame):
        """Process face recognition for a single object (optimized method)"""
        x1, y1, x2, y2 = obj['box']
        # Ensure coordinates are within frame bounds
        x1, y1, x2, y2 = max(0, x1), max(0, y1), min(frame.shape[1], x2), min(frame.shape[0], y2)
        
        # Crop ROI for the selected person
        roi = frame[y1:y2, x1:x2]
        
        if roi.size > 0:
            h_roi, w_roi, _ = roi.shape
            
            # Skip very small ROIs to avoid unnecessary processing
            if h_roi < 50 or w_roi < 50:
                obj['face_id'] = "ROI too small"
                return
            
            # Calculate padding to make ROI square
            pad_left, pad_top = 0, 0
            if h_roi > w_roi:
                pad_size = (h_roi - w_roi) // 2
                padded_roi = cv2.copyMakeBorder(roi, 0, 0, pad_size, pad_size, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                pad_left = pad_size
            elif w_roi > h_roi:
                pad_size = (w_roi - h_roi) // 2
                padded_roi = cv2.copyMakeBorder(roi, pad_size, pad_size, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])
                pad_top = pad_size
            else: # Already square
                padded_roi = roi
            
            # Use smaller size for face detection to improve speed
            detection_size = 320  # YuNet requires fixed 320x320
            resized_roi = cv2.resize(padded_roi, (detection_size, detection_size))
            
            # Detect faces in the ROI using YuNet
            retval, faces_in_roi = self.yunet_detector.detect(resized_roi)
            
            if retval and faces_in_roi is not None and len(faces_in_roi) > 0:
                # Take the first detected face
                x1_det, y1_det, w_det, h_det = map(int, faces_in_roi[0][:4])

                # Scale factor from detection_size to padded_roi size
                scale_factor = padded_roi.shape[0] / 320  # Fixed 320x320 input size

                # Adjust face_rect_roi coordinates back to the padded ROI scale
                x1_scaled = int(x1_det * scale_factor)
                y1_scaled = int(y1_det * scale_factor)
                w_scaled = int(w_det * scale_factor)
                h_scaled = int(h_det * scale_factor)

                # Un-pad to get coordinates relative to the original 'roi'
                x1_unpadded = x1_scaled - pad_left
                y1_unpadded = y1_scaled - pad_top
                
                # Calculate corresponding bottom-right
                x2_unpadded = x1_unpadded + w_scaled
                y2_unpadded = y1_unpadded + h_scaled

                # Convert to (top, right, bottom, left) format relative to original 'roi'
                face_rect_roi_unpadded = (y1_unpadded, x2_unpadded, y2_unpadded, x1_unpadded)
                
                # Convert face_rect_roi_unpadded coordinates to original frame coordinates
                top_orig = face_rect_roi_unpadded[0] + y1
                right_orig = face_rect_roi_unpadded[1] + x1
                bottom_orig = face_rect_roi_unpadded[2] + y1
                left_orig = face_rect_roi_unpadded[3] + x1
                face_rect_original_frame = (top_orig, right_orig, bottom_orig, left_orig)
                
                obj['face_rect'] = face_rect_original_frame

                # Only compute face encodings if we have a reasonable face size
                face_height = bottom_orig - top_orig
                face_width = right_orig - left_orig
                if face_height > 40 and face_width > 40:
                    rgb_frame_for_encoding = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    enc_list = face_recognition.face_encodings(rgb_frame_for_encoding, [face_rect_original_frame])
                    
                    if enc_list:
                        encoding = enc_list[0]
                        match_found = False
                        
                        if self.known_faces_db: # Only try matching if we have known faces
                            # Optimize: pre-compute known encodings list (could be cached further)
                            known_encodings_flat = []
                            known_ids_flat = []
                            for face_id, data in self.known_faces_db.items():
                                # Use only the most recent encoding for faster comparison
                                if data['encodings']:
                                    known_encodings_flat.append(data['encodings'][-1])
                                    known_ids_flat.append(face_id)
                            
                            if known_encodings_flat:
                                distances = face_recognition.face_distance(known_encodings_flat, encoding)
                                best_idx = np.argmin(distances)
                                if distances[best_idx] < self.FACE_RECOGNITION_DISTANCE_THRESHOLD:
                                    fid = known_ids_flat[best_idx]
                                    face_confidence = 1.0 - distances[best_idx]
                                    obj.update({
                                        'face_id': fid,
                                        'name': self.known_faces_db[fid].get('name', 'Unknown'),
                                        'face_confidence': face_confidence
                                    })
                                    
                                    # Cache the result
                                    self.face_cache[self.selected_person_id] = {
                                        'face_id': fid,
                                        'name': self.known_faces_db[fid].get('name', 'Unknown'),
                                        'face_confidence': face_confidence,
                                        'face_rect': face_rect_original_frame,
                                        'frame': self.frame_count
                                    }
                                    
                                    # Add new encoding to the deque for continuous learning if not too close
                                    if distances[best_idx] > self.MIN_DISTINCT_FACE_DISTANCE:
                                        self.known_faces_db[fid]['encodings'].append(encoding)
                                    match_found = True
                        
                        if not match_found:
                            # Assign new "Unidentified" ID if no match is found
                            new_unidentified_id = f"Unidentified_{self.next_person_id_counter}"
                            self.next_person_id_counter += 1
                            
                            # Extract face image from original frame using corrected coordinates
                            face_img = frame[top_orig:bottom_orig, left_orig:right_orig]
                            self.known_faces_db[new_unidentified_id] = {
                                'encodings': deque([encoding], maxlen=self.MAX_FACE_IMAGES_PER_PERSON),
                                'image': cv2.resize(face_img, (100, 100)) if face_img.size > 0 else None,
                                'name': 'Unknown'
                            }
                            obj['face_id'] = new_unidentified_id
                            obj['name'] = 'Unknown'
                            
                            # Cache the result
                            self.face_cache[self.selected_person_id] = {
                                'face_id': new_unidentified_id,
                                'name': 'Unknown',
                                'face_confidence': 0.0,
                                'face_rect': face_rect_original_frame,
                                'frame': self.frame_count
                            }
                    else:
                        obj['face_id'] = "No encoding found"
                else:
                    obj['face_id'] = "Face too small"
            else:
                obj['face_id'] = "No face detected"
        else:
            obj['face_id'] = "Invalid ROI"

    # ---------------------- Drawing Overlays ----------------------
    def draw_overlays(self, frame, tracked_objects):
        for track_id, obj in tracked_objects.items():
            x1, y1, x2, y2 = obj['box']
            centroid_x, centroid_y = obj['centroid']
            name = obj.get('name', 'Unknown')
            face_id = obj.get('face_id', '')

            color = self.BOX_COLORS["unidentified"]
            if face_id and face_id != "No Face Detected":
                if face_id.startswith("Unidentified_"):
                    color = self.BOX_COLORS["unknown"]
                else:
                    color = self.BOX_COLORS["recognized"]

            # Highlight selected person
            if track_id == self.selected_person_id:
                color = (255, 255, 0) # Yellow for selected person

            # Draw bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

            # Draw label background
            label = f"ID: {track_id} {name}"
            (text_w, text_h), baseline = cv2.getTextSize(label, self.FONT, self.FONT_SCALE, self.FONT_THICKNESS)
            cv2.rectangle(frame, (x1, y1 - text_h - baseline), (x1 + text_w, y1), color, -1)
            cv2.putText(frame, label, (x1, y1 - baseline), self.FONT, self.FONT_SCALE, (255, 255, 255), self.FONT_THICKNESS, cv2.LINE_AA)

            # Draw face rectangle if available
            if obj.get('face_rect'):
                top, right, bottom, left = obj['face_rect']
                face_center_x = (left + right) // 2
                face_center_y = (top + bottom) // 2
                face_radius = max(right - left, bottom - top) // 2

                if track_id == self.selected_person_id:
                    # Draw a circle if following
                    cv2.circle(frame, (face_center_x, face_center_y), face_radius, self.BOX_COLORS["face"], 2)
                    cv2.putText(frame, f"Face: {face_id}", (left, top - 10), self.FONT, self.FONT_SCALE * 0.7, self.BOX_COLORS["face"], 2, cv2.LINE_AA)
                else:
                    # Draw a square if not following
                    cv2.rectangle(frame, (left, top), (right, bottom), self.BOX_COLORS["face"], 2)
                    cv2.putText(frame, f"Face: {face_id}", (left, top - 10), self.FONT, self.FONT_SCALE * 0.7, self.BOX_COLORS["face"], 2, cv2.LINE_AA)
        return frame
