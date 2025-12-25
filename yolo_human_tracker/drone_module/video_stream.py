import cv2
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage
import time
import numpy as np
import logging

class VideoStreamThread(QThread):
    change_pixmap_signal = pyqtSignal(QImage)
    update_info_signal = pyqtSignal(dict)
    update_fps_signal = pyqtSignal(int)
    face_count_signal = pyqtSignal(int)
    error_signal = pyqtSignal(str)

    def __init__(self, backend, stream_url, parent=None):
        super().__init__(parent)
        self._run = True
        self.backend = backend
        self.stream_url = stream_url
        logging.info(f"Attempting to open video stream with URL/Index: {self.stream_url}")
        
        if isinstance(self.stream_url, str):
            if self.stream_url.startswith(('http://', 'https://')):
                # For HTTP/HTTPS IP camera streams (like phone cameras)
                self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
                # Set properties for IP cameras
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer for lower latency
                self.cap.set(cv2.CAP_PROP_FPS, 30)  # Set desired FPS
            elif self.stream_url.startswith('rtsp://'):
                # Use cv2.CAP_FFMPEG for RTSP streams
                self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
                # Add buffer size to help with network streams
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3)
                # Explicitly set the video codec to MJPEG
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            else:
                # Other string URLs
                self.cap = cv2.VideoCapture(self.stream_url)
        else:
            # For local cameras (index), do not use CAP_FFMPEG
            self.cap = cv2.VideoCapture(self.stream_url)
            # Set properties for local cameras
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
        
        if not self.cap.isOpened():
            self._run = False
            self.error_signal.emit(f"Error: Could not open video stream at {self.stream_url}.")
            logging.error(f"Failed to open video stream at {self.stream_url}")
        else:
            logging.info(f"Successfully opened video stream at {self.stream_url}")
            # Log camera properties
            width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            logging.info(f"Camera properties - Width: {width}, Height: {height}, FPS: {fps}")
        
        self.prev_frame_time = 0
        self.frame_width = 0
        self.frame_height = 0

    @property
    def original_frame_width(self):
        return self.frame_width

    @property
    def original_frame_height(self):
        return self.frame_height

    def run(self):
        while self._run:
            if not self.backend.paused:
                ret, frame = self.cap.read()
                if not ret:
                    self.error_signal.emit("Error: Failed to read frame from video stream.")
                    logging.warning("Failed to read frame from video stream.")
                    time.sleep(0.1)
                    continue 
                
                if frame is None:
                    logging.warning("Received empty frame from video stream.")
                    time.sleep(0.1)
                    continue

                self.frame_height, self.frame_width, _ = frame.shape

                display_frame, tracked_objects, _ = self.backend.process_frame(frame.copy())

                if display_frame is None:
                    logging.warning("Received empty display_frame after processing.")
                    time.sleep(0.1)
                    continue

                rgb_image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                convert_to_qt_format = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                
                p = convert_to_qt_format.scaled(800, 600, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.change_pixmap_signal.emit(p)

                current_frame_time = time.time()
                fps = 1 / (current_frame_time - self.prev_frame_time) if self.prev_frame_time > 0 else 0
                self.prev_frame_time = current_frame_time
                # Prepare info for HT panel
                info_data = {
                    'name': 'N/A',
                    'id': 'N/A',
                    'confidence': 'N/A',
                    'distance': 'N/A',
                    'image': None
                }

                if self.backend.selected_person_id is not None:
                    selected_obj = tracked_objects.get(self.backend.selected_person_id)
                    if selected_obj:
                        info_data['id'] = self.backend.selected_person_id
                        info_data['name'] = selected_obj.get('name', 'Unknown')
                        info_data['confidence'] = selected_obj.get('face_confidence', 0.0)
                        info_data['distance'] = selected_obj.get('smoothed_distance', 0.0)
                        
                        # Extract face image if available
                        face_rect = selected_obj.get('face_rect')
                        if face_rect:
                            top, right, bottom, left = face_rect
                            # Ensure coordinates are within frame bounds for cropping
                            top = max(0, top)
                            bottom = min(frame.shape[0], bottom)
                            left = max(0, left)
                            right = min(frame.shape[1], right)
                            
                            if bottom > top and right > left:
                                info_data['image'] = frame[top:bottom, left:right]
                                # Convert to RGB for proper display in QLabel
                                if info_data['image'].size > 0:
                                    info_data['image'] = cv2.cvtColor(info_data['image'], cv2.COLOR_BGR2RGB)
                    else:
                        info_data['name'] = 'Person Lost'
                        info_data['id'] = self.backend.selected_person_id
                else: # No person selected
                    info_data['name'] = 'No Person Selected'
                    info_data['id'] = 'No Person Selected'
                self.update_info_signal.emit(info_data)
                self.update_fps_signal.emit(int(fps))
                self.face_count_signal.emit(len(tracked_objects))


    def stop(self):
        self._run = False
        if self.cap.isOpened():
            self.cap.release()
            logging.info("RTSP video stream released.") # Updated log
        self.wait()