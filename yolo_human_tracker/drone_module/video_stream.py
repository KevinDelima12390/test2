import cv2
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage
import time
import numpy as np

def detect_available_cameras():
    """
    Scans for and returns a list of available camera indices.
    """
    available_cameras = []
    for i in range(10):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                available_cameras.append(i)
            cap.release()
    print(f"Detected available cameras: {available_cameras}")
    return available_cameras

class VideoStreamThread(QThread):
    """
    A QThread subclass responsible for handling the video stream from the camera
    and processing frames using the HumanTrackerBackend.
    """
    change_pixmap_signal = pyqtSignal(QImage)
    update_info_signal = pyqtSignal(dict)
    update_fps_signal = pyqtSignal(int)
    face_count_signal = pyqtSignal(int) # New signal for face count
    error_signal = pyqtSignal(str)
    camera_name_signal = pyqtSignal(str)

    def __init__(self, backend, camera_index, parent=None):
        super().__init__(parent)
        self._run = True
        self.backend = backend
        self.camera_index = camera_index
        self.cap = cv2.VideoCapture(self.camera_index)
        
        if not self.cap.isOpened():
            self._run = False
            self.error_signal.emit(f"Error: Could not open camera index {self.camera_index}.")
        else:
            try:
                camera_name = self.cap.getBackendName()
            except Exception:
                camera_name = f"Camera {self.camera_index}"
            self.camera_name_signal.emit(camera_name)
            
        self.prev_frame_time = 0

    def run(self):
        while self._run:
            if not self.backend.paused:
                ret, frame = self.cap.read()
                if not ret:
                    self.error_signal.emit("Error: Failed to read frame from camera.")
                    time.sleep(0.1)
                    continue 
                
                display_frame, tracked_objects, known_faces_db = self.backend.process_frame(frame.copy())

                # Emit face count
                self.face_count_signal.emit(len(tracked_objects))

                rgb_image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                convert_to_qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                p = convert_to_qt_format.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.change_pixmap_signal.emit(p)

                current_frame_time = time.time()
                fps = 1 / (current_frame_time - self.prev_frame_time) if self.prev_frame_time > 0 else 0
                self.prev_frame_time = current_frame_time
                self.update_fps_signal.emit(int(fps))

                recognized_person_data = self.backend.get_recognized_person_data()
                
                if recognized_person_data:
                    face_id = recognized_person_data.get('face_id') 
                    confidence = recognized_person_data.get('face_confidence', 0.0) 
                    person_name = known_faces_db.get(face_id, {}).get('name', 'Unknown')
                    ref_image_bgr = known_faces_db.get(face_id, {}).get('image') 

                    if isinstance(ref_image_bgr, np.ndarray) and ref_image_bgr.size > 0:
                        ref_image_rgb = cv2.cvtColor(ref_image_bgr, cv2.COLOR_BGR2RGB)
                        self.update_info_signal.emit({
                            "name": person_name,
                            "id": face_id,
                            "confidence": f"{confidence:.2f}",
                            "image": ref_image_rgb 
                        })
                    else:
                        self.update_info_signal.emit({
                            "name": person_name,
                            "id": face_id,
                            "confidence": f"{confidence:.2f}",
                            "image": None 
                        })
                else:
                    self.update_info_signal.emit({"name": "N/A", "id": "N/A", "confidence": "N/A", "image": None})

            time.sleep(0.03)

    def stop(self):
        self._run = False
        if self.cap.isOpened():
            self.cap.release()
        self.wait()