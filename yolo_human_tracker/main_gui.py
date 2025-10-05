import sys
import asyncio
import qasync
import os
import cv2
import numpy as np
import threading # Import threading
import sqlite3 # Import sqlite3 for direct DB access
import time # Import time for timestamping log messages
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QLabel, QPushButton, QInputDialog, 
                             QGroupBox, QTextEdit) # Added QTextEdit
from PyQt6.QtGui import QPalette, QColor, QImage, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QUrl, pyqtSlot, QTimer, QTimer
from PyQt6.QtGui import QPixmap
import webbrowser # Import webbrowser

import requests # Import requests for HTTP calls
import sqlite3 # Import sqlite3 for direct DB access

from drone_module.websocket_bridge import WebSocketBridge
from drone_module.gimbal_control import GimbalControl
# from map_widget import MapWidget # Removed MapWidget import
from drone_module.waypoint_deployer import WaypointDeployer
from drone_module.human_tracker_backend import HumanTrackerBackend
from drone_module.video_stream import VideoStreamThread, detect_available_cameras

# Import the Flask app from map_server.py
from map_server import app as flask_app, coords as map_coords

def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()



class Communicate(QObject):
    message_received = pyqtSignal(dict)
    ibis_message_received = pyqtSignal(dict) # New signal for IBIS messages



class DroneControlGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Ground Control Station")
        self.setGeometry(100, 100, 1800, 1000)

        self.pan = 0
        self.tilt = 0
        self.mission_timer = None

        self.set_dark_theme()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Setup background asyncio loop
        self.async_loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=start_async_loop, args=(self.async_loop,), daemon=True)
        self.async_thread.start()

        # Start Flask server in a separate thread
        self.flask_thread = threading.Thread(target=self._run_flask_server, daemon=True)
        self.flask_thread.start()
        time.sleep(1) # Give Flask a moment to start
        webbrowser.open("http://127.0.0.1:5050") # Open map in browser

        # Backends
        self.ws_bridge = WebSocketBridge()
        self.ht_backend = HumanTrackerBackend()

        # Communication
        self.comm = Communicate()
        self.comm.message_received.connect(self.handle_ws_message)
        self.comm.ibis_message_received.connect(self.handle_ibis_ws_message) # Connect new signal
        self.ws_bridge.message_callback = self.queue_ws_message
        self.ws_bridge.ibis_message_callback = self.queue_ibis_ws_message # Assign IBIS callback

        self.create_main_layout()

        # Camera Setup
        self.setup_camera()

        # Start IBIS WebSocket client in the background asyncio loop
        asyncio.run_coroutine_threadsafe(
            self.ws_bridge.connect_to_ibis_ws("ws://127.0.0.1:8000/ws/arc_engine", self.ws_bridge.ibis_message_callback),
            self.async_loop
        )

        # Load IBIS users for facial recognition directly from DB file
        self.load_ibis_users_from_db_file()

        # Setup timer for monitoring new IBIS images
        self.ibis_image_monitor_timer = QTimer(self)
        self.ibis_image_monitor_timer.setInterval(5000) # Check every 5 seconds
        self.ibis_image_monitor_timer.timeout.connect(self.check_for_new_ibis_images)
        self.ibis_image_monitor_timer.start()
        self.known_ibis_images = set() # To keep track of images already processed

        # Telemetry Simulator (for testing map updates)
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.setInterval(1000) # Update every 1 second
        self.telemetry_timer.timeout.connect(self.simulate_telemetry)
        self.telemetry_timer.start()

        self._sim_lat = 3.1275
        self._sim_lon = 101.6579
        self._sim_lat_direction = 0.0001
        self._sim_lon_direction = 0.0001

    def _run_flask_server(self):
        flask_app.run(host="0.0.0.0", port=5050, debug=False)

    def simulate_telemetry(self):
        # Simulate drone movement
        self._sim_lat += self._sim_lat_direction
        self._sim_lon += self._sim_lon_direction

        # Reverse direction if out of bounds (simple bouncing)
        if self._sim_lat > 3.1300 or self._sim_lat < 3.1250:
            self._sim_lat_direction *= -1
        if self._sim_lon > 101.6600 or self._sim_lon < 101.6550:
            self._sim_lon_direction *= -1

        telemetry_message = {
            "type": "telemetry",
            "drone_id": "SIM-DRONE-01",
            "telemetry": {
                "lat": self._sim_lat,
                "lon": self._sim_lon,
                "altitude_m": 100,
                "speed_kmh": 10,
                "battery_pct": 90,
                "heading_deg": 45,
                "flight_time_s": 3600
            },
            "gimbal": {"pan_deg": 0, "tilt_deg": 0}
        }
        self.comm.message_received.emit(telemetry_message)

    def create_main_layout(self):
        main_horizontal_layout = QHBoxLayout()
        self.main_layout.addLayout(main_horizontal_layout)

        # --- Left Panel ---
        left_panel = QVBoxLayout()
        main_horizontal_layout.addLayout(left_panel, 1)

        # Map View (now in external browser)
        map_group = QGroupBox("Map View (External Browser)")
        left_panel.addWidget(map_group)
        map_layout = QVBoxLayout(map_group)
        self.map_status_label = QLabel("Map opened in your default web browser.")
        self.map_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        map_layout.addWidget(self.map_status_label)

        # Waypoint Deployer
        waypoint_group = QGroupBox("Mission Waypoints")
        left_panel.addWidget(waypoint_group)
        waypoint_layout = QVBoxLayout(waypoint_group)
        self.waypoint_deployer = WaypointDeployer()
        self.waypoint_deployer.start_mission.connect(self.start_mission_animation)
        waypoint_layout.addWidget(self.waypoint_deployer)

        self.clear_waypoints_button = QPushButton("Clear Map Waypoints")
        self.clear_waypoints_button.clicked.connect(self.clear_map_waypoints)
        waypoint_layout.addWidget(self.clear_waypoints_button)


        # --- Center Panel: Video Feed ---
        self.video_label = QLabel("Initializing Camera...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        main_horizontal_layout.addWidget(self.video_label, 3)

        # --- Right Panel ---
        right_panel = QVBoxLayout()
        main_horizontal_layout.addLayout(right_panel, 1)

        # Drone Telemetry
        telemetry_group = QGroupBox("Drone Telemetry")
        right_panel.addWidget(telemetry_group)
        telemetry_layout = QVBoxLayout(telemetry_group)
        self.telemetry_dashboard = QLabel("Waiting for drone connection...")
        self.telemetry_dashboard.setAlignment(Qt.AlignmentFlag.AlignTop)
        telemetry_layout.addWidget(self.telemetry_dashboard)

        # Human Tracker Info
        ht_info_group = QGroupBox("Human Tracker Info")
        right_panel.addWidget(ht_info_group)
        ht_info_layout = QVBoxLayout(ht_info_group)
        self.ht_name_label = QLabel("Name: N/A")
        self.ht_id_label = QLabel("ID: N/A")
        self.ht_confidence_label = QLabel("Confidence: N/A")
        self.ht_face_image_label = QLabel("No Face")
        self.ht_face_image_label.setFixedSize(120, 120)
        self.ht_face_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fps_label = QLabel("FPS: 0")
        self.face_count_label = QLabel("Faces: 0") # New label for face count
        ht_info_layout.addWidget(self.ht_name_label)
        ht_info_layout.addWidget(self.ht_id_label)
        ht_info_layout.addWidget(self.ht_confidence_label)
        ht_info_layout.addWidget(self.ht_face_image_label)
        ht_info_layout.addWidget(self.fps_label)
        ht_info_layout.addWidget(self.face_count_label) # Add face count label
        ht_info_layout.addStretch()

        # Notification/Log Area
        self.notification_log = QTextEdit()
        self.notification_log.setReadOnly(True)
        self.notification_log.setPlaceholderText("System notifications and logs will appear here...")
        right_panel.addWidget(self.notification_log)

        # --- Bottom Panel: Controls ---
        bottom_panel = QHBoxLayout()
        self.main_layout.addLayout(bottom_panel)

        # Drone Controls
        drone_controls_group = QGroupBox("Drone Controls")
        bottom_panel.addWidget(drone_controls_group)
        drone_controls_layout = QHBoxLayout(drone_controls_group)
        self.gimbal_control = GimbalControl()
        self.gimbal_control.gimbal_command.connect(self.send_gimbal_command)
        drone_controls_layout.addWidget(self.gimbal_control)

        # Human Tracker Controls
        ht_controls_group = QGroupBox("Human Tracker Controls")
        bottom_panel.addWidget(ht_controls_group)
        ht_controls_layout = QHBoxLayout(ht_controls_group)
        self.fr_toggle_button = QPushButton("FR: Off")
        self.fr_toggle_button.clicked.connect(self.toggle_fr)
        self.ll_toggle_button = QPushButton("Low Light: Off")
        self.ll_toggle_button.clicked.connect(self.toggle_ll)
        self.name_button = QPushButton("Name Unidentified")
        self.name_button.clicked.connect(self.name_person)
        self.edit_name_button = QPushButton("Edit Name")
        self.edit_name_button.clicked.connect(self.edit_name)
        ht_controls_layout.addWidget(self.fr_toggle_button)
        ht_controls_layout.addWidget(self.ll_toggle_button)
        ht_controls_layout.addWidget(self.name_button)
        ht_controls_layout.addWidget(self.edit_name_button)

        self.save_new_face_button = QPushButton("Save New Face")
        self.save_new_face_button.clicked.connect(self.save_new_face_dialog)
        ht_controls_layout.addWidget(self.save_new_face_button)

    def setup_camera(self):
        available_cameras = detect_available_cameras()
        if not available_cameras:
            self.log_message("Camera Error: No cameras found!")
            sys.exit(1)

        if len(available_cameras) > 1:
            item, ok = QInputDialog.getItem(self, "Select Camera", "Choose a camera:", 
                                          [f"Camera {i}" for i in available_cameras], 0, False)
            if ok and item:
                self.camera_index = available_cameras[int(item.split()[-1])]
            else:
                sys.exit(0)
        else:
            self.camera_index = available_cameras[0]
        
        self.start_video_stream()

    def start_video_stream(self):
        try:
            self.log_message(f"Starting video stream with camera index: {self.camera_index}")
            self.video_thread = VideoStreamThread(self.ht_backend, self.camera_index, self)
            self.video_thread.change_pixmap_signal.connect(self.update_image)
            self.video_thread.update_info_signal.connect(self.update_ht_info_panel)
            self.video_thread.update_fps_signal.connect(self.update_fps)
            self.video_thread.face_count_signal.connect(self.update_face_count) # Connect new signal
            self.video_thread.start()
        except Exception as e:
            self.log_message(f"Error starting video stream: {e}")

    def start_server_task(self):
        asyncio.ensure_future(self.ws_bridge.start_server())

    def queue_ws_message(self, message):
        print(f"[MAIN_GUI] queue_ws_message received: {message.get('type')}")
        self.comm.message_received.emit(message)

    def queue_ibis_ws_message(self, message):
        self.comm.ibis_message_received.emit(message)

    def update_map_position(self, message):
        telemetry = message.get('telemetry', {})
        lat = telemetry.get('lat')
        lon = telemetry.get('lon')
        if lat is not None and lon is not None:
            print(f"[MAIN_GUI] Sending map update to Flask: Lat={lat}, Lon={lon}")
            # Update Flask server with new coordinates
            try:
                requests.get(f"http://127.0.0.1:5050/update/{lat}/{lon}")
            except requests.exceptions.ConnectionError:
                self.log_message("Error: Could not connect to map server. Is it running?")

    def handle_ws_message(self, message):
        print(f"[MAIN_GUI] handle_ws_message received: {message.get('type')}")
        if message.get('type') == 'telemetry':
            self.update_telemetry_dashboard(message)
            self.update_map_position(message)

    def handle_ibis_ws_message(self, message):
        if message.get('type') == 'emergency':
            user_id = message.get('user_id')
            lat = message.get('lat')
            lon = message.get('lon')
            if user_id and lat is not None and lon is not None:
                self.log_message(f"Emergency Alert: {user_id} at Lat: {lat}, Lon: {lon}")
                waypoint_str = f"{lat},{lon},{user_id}" # Store user_id with waypoint
                self.waypoint_deployer.add_waypoint(waypoint_str)
                # Send waypoint to Flask map server
                try:
                    requests.get(f"http://127.0.0.1:5050/add_waypoint/{lat}/{lon}")
                except requests.exceptions.ConnectionError:
                    self.log_message("Error: Could not connect to map server to add waypoint.")

    def log_message(self, message):
        self.notification_log.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def load_ibis_users_from_db_file(self):
        DB_PATH = "/Users/kevinarthurdelima/Desktop/test2/ibis_database_system/ibis.db"
        users_data = []
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, name, face_encoding, image_path FROM users")
            rows = cursor.fetchall()
            for row in rows:
                user_id, name, face_encoding, image_path = row
                users_data.append({
                    "user_id": user_id,
                    "name": name,
                    "face_encoding": face_encoding,
                    "image_path": image_path
                })
            conn.close()
            self.ht_backend.import_ibis_faces(users_data)
            self.log_message(f"Loaded {len(users_data)} users from IBIS DB for facial recognition.")
        except sqlite3.Error as e:
            self.log_message(f"IBIS DB Error: Could not load users from IBIS DB: {e}")
        except Exception as e:
            self.log_message(f"IBIS Integration Error: An unexpected error occurred: {e}")

    def check_for_new_ibis_images(self):
        UPLOADS_DIR = "/Users/kevinarthurdelima/Desktop/test2/ibis_database_system/uploads/"
        if not os.path.exists(UPLOADS_DIR):
            return

        current_files = set(os.listdir(UPLOADS_DIR))
        new_files = current_files - self.known_ibis_images

        if new_files:
            self.log_message(f"Detected new IBIS image files: {new_files}. Re-importing users...")
            self.load_ibis_users_from_db_file()
            self.known_ibis_images = current_files # Update known files after re-import

    def set_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setPalette(dark_palette)

    def update_image(self, qt_image):
        self.video_label.setPixmap(QPixmap.fromImage(qt_image))

    def update_ht_info_panel(self, info_data):
        self.ht_name_label.setText(f"Name: {info_data['name']}")
        self.ht_id_label.setText(f"ID: {info_data['id']}")
        self.ht_confidence_label.setText(f"Confidence: {info_data['confidence']}")
        if info_data['image'] is not None and isinstance(info_data['image'], np.ndarray):
            h, w, ch = info_data['image'].shape
            bytes_per_line = ch * w
            qt_image = QImage(info_data['image'].data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            self.ht_face_image_label.setPixmap(QPixmap.fromImage(qt_image).scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.ht_face_image_label.setText("No Face")

    def update_fps(self, fps):
        self.fps_label.setText(f"FPS: {fps}")

    def update_face_count(self, count):
        self.face_count_label.setText(f"Faces: {count}")

    def toggle_fr(self):
        status = self.ht_backend.toggle_face_recognition()
        self.fr_toggle_button.setText(f"FR: {'On' if status else 'Off'}")

    def toggle_ll(self):
        status = self.ht_backend.toggle_low_light_enhancement()
        self.ll_toggle_button.setText(f"Low Light: {'On' if status else 'Off'}")

    def name_person(self):
        unidentified_face_ids = self.ht_backend.get_unidentified_face_ids()
        if unidentified_face_ids:
            item, ok = QInputDialog.getItem(self, "Name Unidentified Person", "Select an Unidentified Person ID:", 
                                          unidentified_face_ids, 0, False)
            if ok and item:
                target_face_id = item
                new_name, ok_name = QInputDialog.getText(self, "Enter Name", f"Enter a name for {target_face_id}:")
                if ok_name and new_name and not new_name.isspace():
                    success, message = self.ht_backend.name_unidentified_person(target_face_id, new_name)
                    if not success:
                        self.log_message(f"Error: {message}")
        else:
            self.log_message("Info: No 'Unidentified' person currently tracked to name.")

    def edit_name(self):
        known_names = self.ht_backend.get_known_person_names()
        if known_names:
            old_name, ok = QInputDialog.getItem(self, "Edit Person's Name", "Select a person to rename:",
                                            known_names, 0, False)
            if ok and old_name:
                new_name, ok_name = QInputDialog.getText(self, "Enter New Name", f"Enter a new name for {old_name}:")
                if ok_name and new_name and not new_name.isspace():
                    success, message = self.ht_backend.edit_person_name(old_name, new_name)
                    if not success:
                        self.log_message(f"Error: {message}")
        else:
            self.log_message("Info: No named people in the database to edit.")

    def save_new_face_dialog(self):
        # Get currently detected faces that are not yet identified
        detected_faces_info = self.ht_backend.get_current_unidentified_faces_for_saving()

        if not detected_faces_info:
            self.log_message("Info: No new faces detected in the current frame to save.")
            return

        # Present options to the user
        face_options = [f"ID: {info['temp_id']} (Confidence: {info['confidence']:.2f})" for info in detected_faces_info]
        selected_option, ok = QInputDialog.getItem(self, "Save New Face", "Select a face to save:", face_options, 0, False)

        if ok and selected_option:
            # Extract the temporary ID from the selected option string
            temp_id = selected_option.split(' ')[1]
            selected_face_data = next((info for info in detected_faces_info if info['temp_id'] == temp_id), None)

            if selected_face_data:
                new_name, ok_name = QInputDialog.getText(self, "Enter Name", f"Enter a name for {selected_face_data['temp_id']}:")
                if ok_name and new_name and not new_name.isspace():
                    success, message = self.ht_backend.save_new_face(selected_face_data['encoding'], new_name)
                    if success:
                        self.log_message(f"Save New Face: {message}")
                    else:
                        self.log_message(f"Save New Face Error: {message}")
            else:
                self.log_message("Save New Face Error: Selected face data not found.")




    def send_gimbal_command(self, axis, direction):
        if axis == 'pan':
            self.pan += direction
        elif axis == 'tilt':
            self.tilt += direction
        
        command = {
            "type": "command",
            "command": "gimbal",
            "drone_id": "AERIS-01",
            "payload": {"pan_deg": self.pan, "tilt_deg": self.tilt}
        }
        asyncio.run_coroutine_threadsafe(self.ws_bridge.send_to_all(command), self.async_loop)

    def update_telemetry_dashboard(self, message):
        telemetry = message.get('telemetry', {})
        gimbal = message.get('gimbal', {})
        self.pan = gimbal.get('pan_deg', self.pan)
        self.tilt = gimbal.get('tilt_deg', self.tilt)

        text = f"""
        Drone ID: {message.get('drone_id')}
        Lat: {telemetry.get('lat')}
        Lon: {telemetry.get('lon')}
        Altitude: {telemetry.get('altitude_m')} m
        Speed: {telemetry.get('speed_kmh')} km/h
        Battery: {telemetry.get('battery_pct')} %
        Heading: {telemetry.get('heading_deg')} °
        Flight Time: {telemetry.get('flight_time_s')} s
        Gimbal Pan: {self.pan} °
        Gimbal Tilt: {self.tilt} °
        """
        self.telemetry_dashboard.setText(text)



    def start_mission_animation(self, waypoints):
        if not waypoints:
            return

        self.mission_waypoints = []
        for wp_str in waypoints:
            try:
                lat, lon = map(float, wp_str.split(',')[:2]) # Only take lat and lon
                self.mission_waypoints.append((lat, lon))
            except ValueError:
                pass

        if not self.mission_waypoints:
            return

        # Clear existing waypoints on the Flask map server
        try:
            requests.get("http://127.0.0.1:5050/clear_waypoints")
        except requests.exceptions.ConnectionError:
            self.log_message("Error: Could not connect to map server to clear waypoints.")

        # Send all mission waypoints to the Flask map server
        for lat, lon in self.mission_waypoints:
            try:
                requests.get(f"http://127.0.0.1:5050/add_waypoint/{lat}/{lon}")
            except requests.exceptions.ConnectionError:
                self.log_message("Error: Could not connect to map server to add mission waypoint.")

        self.current_waypoint_index = 0
        self.animation_step = 0
        self.animation_steps_per_segment = 100

        if self.mission_timer:
            self.mission_timer.stop()
        self.mission_timer = QTimer(self)
        self.mission_timer.timeout.connect(self.update_mission_animation)
        self.mission_timer.start(100) # Update every 100ms

    def update_mission_animation(self):
        if self.current_waypoint_index >= len(self.mission_waypoints) - 1:
            self.mission_timer.stop()
            return

        start_wp = self.mission_waypoints[self.current_waypoint_index]
        end_wp = self.mission_waypoints[self.current_waypoint_index + 1]

        # Interpolate position
        fraction = self.animation_step / self.animation_steps_per_segment
        lat = start_wp[0] + (end_wp[0] - start_wp[0]) * fraction
        lon = start_wp[1] + (end_wp[1] - start_wp[1]) * fraction

        print(f"[MAIN_GUI] Mission animation sending update: Lat={lat}, Lon={lon}")
        # Update map and telemetry
        try:
            requests.get(f"http://127.0.0.1:5050/update/{lat}/{lon}")
        except requests.exceptions.ConnectionError:
            self.log_message("Error: Could not connect to map server. Is it running?")
        self.update_telemetry_dashboard_with_mission_data(lat, lon)

        self.animation_step += 1
        if self.animation_step > self.animation_steps_per_segment:
            self.animation_step = 0
            self.current_waypoint_index += 1

    def update_telemetry_dashboard_with_mission_data(self, lat, lon):
        text = f"""
        Drone ID: AERIS-01 (Mission)
        Lat: {lat:.6f}
        Lon: {lon:.6f}
        """
        self.telemetry_dashboard.setText(text)

    def clear_map_waypoints(self):
        try:
            requests.get("http://127.0.0.1:5050/clear_waypoints")
            self.log_message("Map waypoints cleared.")
        except requests.exceptions.ConnectionError:
            self.log_message("Error: Could not connect to map server to clear waypoints.")

    def closeEvent(self, event):
        self.video_thread.stop()
        self.ht_backend.save_known_faces()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    gui = DroneControlGUI()
    gui.show()
    gui.start_server_task()

    with loop:
        loop.run_forever()