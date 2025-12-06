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
            # Use cv2.CAP_FFMPEG for RTSP streams
            self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
            # Add buffer size to help with network streams
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 3) # Add this line
            # Explicitly set the video codec to MJPEG
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcode(*'MJPG')) # Add this line
        else:
            # For local cameras, do not use CAP_FFMPEG
            self.cap = cv2.VideoCapture(self.stream_url)
        
        if not self.cap.isOpened():
            self._run = False
            self.error_signal.emit(f"Error: Could not open RTSP stream at {self.stream_url}.") # Updated log
            logging.error(f"Failed to open RTSP video stream at {self.stream_url}") # Updated log
        else:
            logging.info(f"Successfully opened RTSP video stream at {self.stream_url}") # Updated log
        
        self.prev_frame_time = 0

    def run(self):
        while self._run:
            if not self.backend.paused:
                ret, frame = self.cap.read()
                if not ret:
                    self.error_signal.emit("Error: Failed to read frame from RTSP stream.") # Updated log
                    logging.warning("Failed to read frame from RTSP video stream.") # Updated log
                    time.sleep(0.1)
                    continue 
                
                if frame is None:
                    logging.warning("Received empty frame from RTSP video stream.") # Updated log
                    time.sleep(0.1)
                    continue

                display_frame, _, _ = self.backend.process_frame(frame.copy())

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
                self.update_fps_signal.emit(int(fps))

            time.sleep(0.03)

    def stop(self):
        self._run = False
        if self.cap.isOpened():
            self.cap.release()
            logging.info("RTSP video stream released.") # Updated log
        self.wait()