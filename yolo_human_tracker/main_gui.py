import sys
import asyncio
import qasync
import os
import cv2
import numpy as np
import threading # Import threading
import sqlite3 # Import sqlite3 for direct DB access
import time # Import time for timestamping log messages
import pickle
import base64
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QTabWidget, QLabel, QPushButton, QInputDialog, 
                             QGroupBox, QTextEdit, QLineEdit, QComboBox) # Added QTextEdit
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QPalette, QColor, QImage, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QUrl, pyqtSlot, QTimer, QTimer
from PyQt6.QtGui import QPixmap
import webbrowser # Import webbrowser

import math # Import math for radian to degree conversion

import requests # Import requests for HTTP calls
import sqlite3 # Import sqlite3 for direct DB access

from drone_module.websocket_bridge import WebSocketBridge
from drone_module.mavlink_communicator import MavlinkCommunicator
from drone_module.drone_telemetry import DroneTelemetryListener
# from map_widget import MapWidget # Removed MapWidget import
from drone_module.tracker_backend import HumanTrackerBackend
from drone_module.video_stream import VideoStreamThread
from drone_module.attitude_indicator import AttitudeIndicatorWidget
from drone_module.compass_widget import CompassWidget

# IBIS Configuration
IBIS_CONFIG = {
    "BASE_URL": "http://3.25.229.21:8000",
    "WEBSOCKET_URL": "ws://3.25.229.21:8000/ws/arc_engine",
    "USERNAME": "Admin01", # Service account username for the tracker service
    "PASSWORD": "Delima12390", # Service account password
    "TOKEN": None
}

# Gimbal Control Configuration
GIMBAL_CONFIG = {
    "PI_IP": "192.168.0.101",  # IMPORTANT: Update with your Raspberry Pi's IP
    "PORT": 5005
}

# Video Stream from Pi Configuration
UDP_PORT_FOR_PI_STREAM = 5000 # Must match port used by rpicam-vid on Raspberry Pi

# Import the Flask app from map_server.py
# Import the Flask app from map_server.py
# from map_server import app as flask_app, coords as map_coords

from drone_module.gimbal_udp_sender import GimbalUDPSender

def start_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

class Communicate(QObject):
    message_received = pyqtSignal(dict)
    ibis_message_received = pyqtSignal(dict)
    telemetry_received = pyqtSignal(dict)
    drone_connected = pyqtSignal(bool)
    armed_status_changed = pyqtSignal(bool)
    drone_log_received = pyqtSignal(str)

class ClickableVideoLabel(QLabel):
    clicked_coordinates = pyqtSignal(int, int)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked_coordinates.emit(event.pos().x(), event.pos().y())
        super().mousePressEvent(event)

class DroneControlGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ARC_ENGIN")
        self.setGeometry(100, 100, 1800, 1000)

        self.pan = 0
        self.tilt = 0
        self.mission_timer = None

        # Initialize last known telemetry values
        self.last_lat = 0.0
        self.last_lon = 0.0
        self.last_alt = 0.0
        self.last_ground_speed = 0.0
        self.last_battery_voltage = 0.0
        self.last_battery_remaining = 0
        self.last_signal_strength = 0

        self.selected_person_id = None # Initialize selected person ID
        self.video_thread = None

        self.set_dark_theme()

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)

        # Setup background asyncio loop
        self.async_loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=start_async_loop, args=(self.async_loop,), daemon=True)
        self.async_thread.start()

        # Start Flask server in a separate thread
        # self.flask_thread = threading.Thread(target=self._run_flask_server, daemon=True)
        # self.flask_thread.start()
        # time.sleep(1) # Give Flask a moment to start
        # webbrowser.open("http://127.0.0.1:5050") # Open map in browser

        # Backends
        self.ws_bridge = WebSocketBridge()
        self.ht_backend = HumanTrackerBackend()
        self.telemetry_listener = DroneTelemetryListener(telemetry_callback=self.queue_telemetry_message)
        self.mavlink_communicator = MavlinkCommunicator()
        self.gimbal_udp_sender = GimbalUDPSender(GIMBAL_CONFIG["PI_IP"], GIMBAL_CONFIG["PORT"])

        self.attitude_indicator = AttitudeIndicatorWidget(self)
        self.compass_widget = CompassWidget(self)

        # Communication
        self.comm = Communicate()
        self.comm.message_received.connect(self.handle_ws_message)
        self.comm.ibis_message_received.connect(self.handle_ibis_ws_message)
        self.comm.telemetry_received.connect(self.handle_telemetry_message)
        self.comm.drone_connected.connect(self.update_connection_status)
        self.comm.armed_status_changed.connect(self.update_armed_status)
        self.comm.drone_log_received.connect(self.log_drone_message)
        self.ws_bridge.message_callback = self.queue_ws_message
        self.ws_bridge.ibis_message_callback = self.queue_ibis_ws_message

        self.create_main_layout()

        # Camera Setup
        self.setup_camera()

        # Start background services
        # asyncio.run_coroutine_threadsafe(
        #     self.ws_bridge.connect_to_ibis_ws(IBIS_CONFIG["WEBSOCKET_URL"], self.ws_bridge.ibis_message_callback),
        #     self.async_loop
        # )
        
        self.telemetry_listener.start()

        # self.load_ibis_users_via_api()

    def _run_flask_server(self):
        flask_app.run(host="0.0.0.0", port=5050, debug=False)

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
        self.map_view = QWebEngineView()
        self.map_view.setUrl(QUrl("http://127.0.0.1:5050"))
        map_layout.addWidget(self.map_view)

        # Waypoint Deployer
        waypoint_group = QGroupBox("Mission Waypoints")
        left_panel.addWidget(waypoint_group)
        waypoint_layout = QVBoxLayout(waypoint_group)
        
        self.clear_waypoints_button = QPushButton("Clear Map Waypoints")
        self.clear_waypoints_button.clicked.connect(self.clear_map_waypoints)
        waypoint_layout.addWidget(self.clear_waypoints_button)

        # Camera Selection
        camera_group = QGroupBox("Camera Source")
        left_panel.addWidget(camera_group)
        camera_layout = QVBoxLayout(camera_group)
        
        self.camera_combo = QComboBox()
        self.camera_combo.addItem("Default Camera (0)", 0)
        self.camera_combo.addItem("External Camera (1)", 1)
        self.camera_combo.addItem("IP Camera (Phone)", "ip")
        self.camera_combo.addItem("Raspberry Pi UDP Stream", "udp_pi")
        camera_layout.addWidget(self.camera_combo)
        
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter IP Camera URL (e.g., http://192.168.1.100:8080/video)")
        self.ip_input.setEnabled(False)
        camera_layout.addWidget(self.ip_input)
        
        self.camera_combo.currentTextChanged.connect(self.on_camera_selection_changed)
        
        self.connect_camera_button = QPushButton("Connect Camera")
        self.connect_camera_button.clicked.connect(self.reconnect_camera)
        camera_layout.addWidget(self.connect_camera_button)

        # --- Center Panel: Video Feed ---
        self.video_label = ClickableVideoLabel("Waiting for video stream...")
        self.video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        self.video_label.clicked_coordinates.connect(self.handle_video_click)
        main_horizontal_layout.addWidget(self.video_label, 3)

        # --- Right Panel ---
        right_panel = QVBoxLayout()
        main_horizontal_layout.addLayout(right_panel, 1)

        # Drone Status Indicators
        status_group = QGroupBox("Drone Status")
        right_panel.addWidget(status_group)
        status_layout = QHBoxLayout(status_group)
        self.connection_status_label = QLabel("DISCONNECTED")
        self.connection_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status_label.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.armed_status_label = QLabel("DISARMED")
        self.armed_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.armed_status_label.setStyleSheet("background-color: gray; color: white; font-weight: bold;")
        status_layout.addWidget(self.connection_status_label)
        status_layout.addWidget(self.armed_status_label)

        # Drone Telemetry
        telemetry_group = QGroupBox("Drone Telemetry")
        right_panel.addWidget(telemetry_group)
        telemetry_layout = QVBoxLayout(telemetry_group) # Existing layout for the group

        # New Horizontal Layout for visual indicators
        telemetry_visual_layout = QHBoxLayout()
        telemetry_layout.addLayout(telemetry_visual_layout)
        
        telemetry_visual_layout.addWidget(self.attitude_indicator)
        telemetry_visual_layout.addWidget(self.compass_widget)

        # Simplified text telemetry dashboard
        self.telemetry_dashboard = QLabel("Waiting for drone connection...")
        self.telemetry_dashboard.setAlignment(Qt.AlignmentFlag.AlignTop)
        telemetry_layout.addWidget(self.telemetry_dashboard) # Keep existing text dashboard below visuals

        # Human Tracker Info
        ht_info_group = QGroupBox("Human Tracker Info")
        right_panel.addWidget(ht_info_group)
        ht_info_layout = QVBoxLayout(ht_info_group)
        self.ht_name_label = QLabel("Name: N/A")
        self.ht_id_label = QLabel("ID: N/A")
        self.ht_confidence_label = QLabel("Confidence: N/A")
        self.ht_distance_label = QLabel("Distance: N/A")  # New distance label
        self.ht_face_image_label = QLabel("No Face")
        self.ht_face_image_label.setFixedSize(120, 120)
        self.ht_face_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fps_label = QLabel("FPS: 0")
        self.face_count_label = QLabel("Faces: 0") # New label for face count
        ht_info_layout.addWidget(self.ht_name_label)
        ht_info_layout.addWidget(self.ht_id_label)
        ht_info_layout.addWidget(self.ht_confidence_label)
        ht_info_layout.addWidget(self.ht_distance_label)  # Add distance label
        ht_info_layout.addWidget(self.ht_face_image_label)
        ht_info_layout.addWidget(self.fps_label)
        ht_info_layout.addWidget(self.face_count_label) # Add face count label
        ht_info_layout.addStretch()

        # Log and Console Tabs
        self.log_tabs = QTabWidget()
        right_panel.addWidget(self.log_tabs)

        # System Log Tab
        self.system_log = QTextEdit()
        self.system_log.setReadOnly(True)
        self.log_tabs.addTab(self.system_log, "System Logs")

        # Drone Log Tab
        self.drone_log = QTextEdit()
        self.drone_log.setReadOnly(True)
        self.log_tabs.addTab(self.drone_log, "Drone Logs")

        # MAVLink Console Tab
        self.mavlink_console_widget = QWidget()
        self.log_tabs.addTab(self.mavlink_console_widget, "MAVLink Console")
        console_layout = QVBoxLayout(self.mavlink_console_widget)
        self.mavlink_console_output = QTextEdit()
        self.mavlink_console_output.setReadOnly(True)
        self.mavlink_console_input = QLineEdit()
        self.mavlink_console_input.returnPressed.connect(self.send_mavlink_console_command)
        console_layout.addWidget(self.mavlink_console_output)
        console_layout.addWidget(self.mavlink_console_input)

        # --- Bottom Panel: Controls ---
        bottom_panel = QHBoxLayout()
        self.main_layout.addLayout(bottom_panel)

        

        # Drone Controls

        drone_controls_group = QGroupBox("Drone Controls")

        bottom_panel.addWidget(drone_controls_group)

        drone_controls_layout = QHBoxLayout(drone_controls_group)



        arm_button = QPushButton("Arm")

        arm_button.clicked.connect(self.arm_drone)

        disarm_button = QPushButton("Disarm")

        disarm_button.clicked.connect(self.disarm_drone)

        drone_controls_layout.addWidget(arm_button)

        drone_controls_layout.addWidget(disarm_button)

        diagnostics_button = QPushButton("Run Diagnostics")
        diagnostics_button.clicked.connect(self.run_diagnostics)
        drone_controls_layout.addWidget(diagnostics_button)

        flight_mode_box = QComboBox()
        flight_mode_box.addItems(["Stabilize", "Loiter", "RTL", "Auto"])
        flight_mode_box.textActivated.connect(self.set_flight_mode)
        drone_controls_layout.addWidget(flight_mode_box)

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

    def on_camera_selection_changed(self, text):
        """Handle camera selection change"""
        if "IP Camera" in text:
            self.ip_input.setPlaceholderText("Enter IP Camera URL (e.g., http://192.168.1.100:8080/video)")
            self.ip_input.setEnabled(True)
        elif "Raspberry Pi UDP Stream" in text:
            self.ip_input.setPlaceholderText("Enter UDP Stream Address (e.g., udp://0.0.0.0:5000)")
            self.ip_input.setEnabled(True)
        else:
            self.ip_input.setEnabled(False)
    
    def reconnect_camera(self):
        """Reconnect to the selected camera source"""
        if self.video_thread:
            self.video_thread._run = False
            self.video_thread.quit()
            self.video_thread.wait()
        
        self.start_video_stream()
    
    def setup_camera(self):
        self.start_video_stream()

    def start_video_stream(self):
        try:
            # Determine camera source based on selection
            current_selection = self.camera_combo.currentData()
            
            if current_selection == "ip":
                camera_url = self.ip_input.text().strip()
                if not camera_url:
                    self.log_message("Please enter IP camera URL first")
                    return
                self.log_message(f"Connecting to IP camera: {camera_url}")
            elif current_selection == "udp_pi":
                camera_url = self.ip_input.text().strip()
                if not camera_url:
                    # Provide a default if user doesn't enter anything for UDP
                    camera_url = f"udp://0.0.0.0:{UDP_PORT_FOR_PI_STREAM}" # Define UDP_PORT_FOR_PI_STREAM as 5000 earlier
                    self.log_message(f"Using default Raspberry Pi UDP stream address: {camera_url}")
                else:
                    self.log_message(f"Connecting to Raspberry Pi UDP stream: {camera_url}")
            else:
                camera_url = current_selection
                self.log_message(f"Starting camera {camera_url}...")
            
            self.video_thread = VideoStreamThread(self.ht_backend, camera_url, self.gimbal_udp_sender, self)
            self.video_thread.change_pixmap_signal.connect(self.update_image)
            self.video_thread.update_info_signal.connect(self.update_ht_info_panel)
            self.video_thread.update_fps_signal.connect(self.update_fps)
            self.video_thread.face_count_signal.connect(self.update_face_count) # Connect new signal
            self.video_thread.error_signal.connect(self.log_message)
            self.video_thread.start()
            self.log_message("Video stream thread started. Waiting for camera to provide frames...")
        except Exception as e:
            self.log_message(f"Error starting video stream: {e}")

    def start_server_task(self):
        asyncio.ensure_future(self.ws_bridge.start_server())

    def queue_ws_message(self, message):
        print(f"[MAIN_GUI] queue_ws_message received: {message.get('type')}")
        self.comm.message_received.emit(message)

    def queue_ibis_ws_message(self, message):
        self.comm.ibis_message_received.emit(message)

    def queue_telemetry_message(self, message):
        self.comm.telemetry_received.emit(message)
        self.comm.drone_log_received.emit(str(message))

    def log_drone_message(self, message):
        self.drone_log.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def handle_telemetry_message(self, message):
        if message.get('status') == 'drone_connected':
            self.comm.drone_connected.emit(True)

        if 'armed' in message:
            self.comm.armed_status_changed.emit(message['armed'])

        self.update_telemetry_dashboard(message)
        self.update_map_position(message)

        # Update visual telemetry widgets
        pitch_rad = message.get('pitch', 0.0) # Assume pitch is in radians
        roll_rad = message.get('roll', 0.0) # Assume roll is in radians
        yaw_rad = message.get('yaw', 0.0) # Assume yaw (heading) is in radians

        # Convert radians to degrees for the widgets
        pitch_deg = math.degrees(pitch_rad)
        roll_deg = math.degrees(roll_rad)
        yaw_deg = math.degrees(yaw_rad)
        
        # Ensure yaw is within 0-360 range
        if yaw_deg < 0:
            yaw_deg += 360
        
        self.attitude_indicator.update_attitude(pitch_deg, roll_deg)
        self.compass_widget.update_heading(yaw_deg)

    def update_connection_status(self, connected):
        if connected:
            self.connection_status_label.setText("CONNECTED")
            self.connection_status_label.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        else:
            self.connection_status_label.setText("DISCONNECTED")
            self.connection_status_label.setStyleSheet("background-color: red; color: white; font-weight: bold;")

    def update_armed_status(self, armed):
        if armed:
            self.armed_status_label.setText("ARMED")
            self.armed_status_label.setStyleSheet("background-color: green; color: white; font-weight: bold;")
        else:
            self.armed_status_label.setText("DISARMED")
            self.armed_status_label.setStyleSheet("background-color: gray; color: white; font-weight: bold;")

    def arm_drone(self):
        self.log_message("Sending ARM command...")
        self.mavlink_communicator.arm_disarm(True)

    def set_flight_mode(self, mode):
        self.log_message(f"Setting flight mode to {mode}")
        self.mavlink_communicator.set_flight_mode(mode)

    def run_diagnostics(self):
        self.log_message("--- Running System Diagnostics ---")
        self.log_message("Checking MAVLink two-way communication...")
        
        # This is a blocking call, so it should be run in a thread 
        # to avoid freezing the GUI. For simplicity, we run it directly here.
        # In a real-world app, consider a background thread.
        success = self.mavlink_communicator.run_diagnostics()

        if success:
            self.log_message("  -> MAVLink Communication: OK")
        else:
            self.log_message("  -> MAVLink Communication: FAILED")

        self.log_message("--- Diagnostics Complete ---")

    def disarm_drone(self):
        self.log_message("Sending DISARM command...")
        self.mavlink_communicator.arm_disarm(False)

    def update_map_position(self, message):
        lat = message.get('latitude')
        lon = message.get('longitude')
        if lat is not None and lon is not None:
            print(f"[MAIN_GUI] Sending map update to Flask: Lat={lat}, Lon={lon}")
            try:
                requests.get(f"http://127.0.0.1:5050/update/{lat}/{lon}")
            except requests.exceptions.ConnectionError:
                self.log_message("Error: Could not connect to map server. Is it running?")

    def handle_ws_message(self, message):
        print(f"[MAIN_GUI] handle_ws_message received: {message.get('type')}")
        # Telemetry is now handled by handle_telemetry_message
        pass

    def handle_ibis_ws_message(self, message):
        if message.get('type') == 'emergency':
            user_id = message.get('user_id')
            lat = message.get('lat')
            lon = message.get('lon')
            if user_id and lat is not None and lon is not None:
                self.log_message(f"Emergency Alert: {user_id} at Lat: {lat}, Lon: {lon}")
                waypoint_str = f"{lat},{lon},{user_id}" # Store user_id with waypoint
                # Send waypoint to Flask map server
                try:
                    requests.get(f"http://127.0.0.1:5050/add_waypoint/{lat}/{lon}")
                except requests.exceptions.ConnectionError:
                    self.log_message("Error: Could not connect to map server to add waypoint.")

    def log_message(self, message):
        self.system_log.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        self.system_log.verticalScrollBar().setValue(self.system_log.verticalScrollBar().maximum())

    def send_mavlink_console_command(self):
        command = self.mavlink_console_input.text()
        if command:
            self.mavlink_console_output.append(f"> {command}")
            self.mavlink_communicator.send_text_command(command)
            self.mavlink_console_input.clear()

    def load_ibis_users_via_api(self):
        """
        Logs into the IBIS API, fetches all users with face encodings,
        and imports them into the human tracker backend.
        """
        self.log_message("Attempting to load IBIS users from API...")

        # 1. Authenticate and get token
        try:
            login_data = {
                "user_id": IBIS_CONFIG["USERNAME"],
                "password": IBIS_CONFIG["PASSWORD"]
            }
            login_url = f"{IBIS_CONFIG['BASE_URL']}/login"
            response = requests.post(login_url, json=login_data)

            if response.status_code != 200:
                self.log_message(f"IBIS API Error: Failed to login. Status: {response.status_code}, Detail: {response.text}")
                return

            IBIS_CONFIG["TOKEN"] = response.json()["access_token"]
            self.log_message("IBIS API: Login successful.")

        except requests.exceptions.RequestException as e:
            self.log_message(f"IBIS API Error: Could not connect to login endpoint: {e}")
            return

        # 2. Fetch users with faces
        try:
            headers = {"Authorization": f"Bearer {IBIS_CONFIG['TOKEN']}"}
            users_url = f"{IBIS_CONFIG['BASE_URL']}/users_with_faces"
            response = requests.get(users_url, headers=headers)

            if response.status_code != 200:
                self.log_message(f"IBIS API Error: Failed to fetch users. Status: {response.status_code}, Detail: {response.text}")
                return
            
            users_data = response.json()

            # 3. Decode face encodings and prepare data for the backend
            processed_users = []
            for user in users_data:
                try:
                    # The encoding from the API is a Base64 encoded string of the pickled numpy array
                    pickled_encoding = base64.b64decode(user["face_encoding"])
                    face_encoding = pickle.loads(pickled_encoding)
                    
                    processed_users.append({
                        "user_id": user["user_id"],
                        "name": user["name"],
                        "face_encoding": face_encoding, # This is now the numpy array
                        "image_path": user.get("image_path", "") # Ensure image_path is present
                    })
                except (pickle.UnpicklingError, base64.binascii.Error, KeyError) as e:
                    self.log_message(f"Error processing user {user.get('user_id', 'N/A')}: Could not decode face encoding. Error: {e}")

            # 4. Import faces into the backend
            self.ht_backend.import_ibis_faces(processed_users)
            self.log_message(f"Loaded {len(processed_users)} users from IBIS API for facial recognition.")

        except requests.exceptions.RequestException as e:
            self.log_message(f"IBIS API Error: Could not fetch users from endpoint: {e}")
        except Exception as e:
            self.log_message(f"IBIS Integration Error: An unexpected error occurred while processing API data: {e}")


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
        
        # Format distance display
        distance = info_data.get('distance', 'N/A')
        if isinstance(distance, (int, float)) and distance != 'N/A':
            self.ht_distance_label.setText(f"Distance: {distance:.1f}m")
        else:
            self.ht_distance_label.setText("Distance: N/A")
        
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

    def handle_video_click(self, x, y):
        if not self.video_thread:
            self.log_message("Video thread not initialized. Cannot handle video click.")
            return
        # Get dimensions of the QLabel and the original frame
        label_width = self.video_label.width()
        label_height = self.video_label.height()
        frame_width = self.video_thread.original_frame_width
        frame_height = self.video_thread.original_frame_height

        if frame_width == 0 or frame_height == 0:
            self.log_message("Video stream not active or frame dimensions unknown.")
            self.ht_backend.set_selected_person(None)
            return

        # Calculate scaling factors, considering aspect ratio
        aspect_ratio_label = label_width / label_height
        aspect_ratio_frame = frame_width / frame_height

        if aspect_ratio_label > aspect_ratio_frame:
            # Label is wider than frame, frame is height-limited
            scaled_frame_width = int(label_height * aspect_ratio_frame)
            scaled_frame_height = label_height
            offset_x = (label_width - scaled_frame_width) / 2
            offset_y = 0
        else:
            # Label is taller than frame, frame is width-limited
            scaled_frame_width = label_width
            scaled_frame_height = int(label_width / aspect_ratio_frame)
            offset_x = 0
            offset_y = (label_height - scaled_frame_height) / 2

        # Convert click coordinates from QLabel to scaled frame
        click_x_scaled = x - offset_x
        click_y_scaled = y - offset_y

        # Convert scaled frame coordinates to original frame coordinates
        original_x = int(click_x_scaled * (frame_width / scaled_frame_width))
        original_y = int(click_y_scaled * (frame_height / scaled_frame_height))

        self.log_message(f"Clicked on QLabel at ({x}, {y}). Converted to original frame coordinates: ({original_x}, {original_y})")

        selected_id = None
        for pid, obj in self.ht_backend.tracked_objects.items():
            x1, y1, x2, y2 = obj['box']
            if x1 <= original_x <= x2 and y1 <= original_y <= y2:
                selected_id = pid
                break
        
        self.ht_backend.set_selected_person(selected_id)
        if selected_id:
            self.log_message(f"Selected person with ID: {selected_id}")
        else:
            self.log_message("No person selected.")

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
        face_options = [f"ID: {info['person_id']}" for info in detected_faces_info]
        selected_option, ok = QInputDialog.getItem(self, "Save New Face", "Select a face to save:", face_options, 0, False)

        if ok and selected_option:
            # Extract the temporary ID from the selected option string
            # It will be in the format "ID: Unidentified_X"
            person_id_from_option = selected_option.split(': ')[1]
            selected_face_data = next((info for info in detected_faces_info if info['person_id'] == person_id_from_option), None)

            if selected_face_data:
                new_name, ok_name = QInputDialog.getText(self, "Enter Name", f"Enter a name for {selected_face_data['person_id']}:")
                if ok_name and new_name and not new_name.isspace():
                    success, message = self.ht_backend.save_new_face(selected_face_data['face_encoding'], new_name)
                    if success:
                        self.log_message(f"Save New Face: {message}")
                    else:
                        self.log_message(f"Save New Face Error: {message}")
            else:
                self.log_message("Save New Face Error: Selected face data not found.")

    def update_telemetry_dashboard(self, message):
        # Store last known values
        if 'latitude' in message: self.last_lat = message.get('latitude')
        if 'longitude' in message: self.last_lon = message.get('longitude')
        if 'altitude' in message: self.last_alt = message.get('altitude')
        if 'ground_speed' in message: self.last_ground_speed = message.get('ground_speed')
        if 'battery_voltage' in message: self.last_battery_voltage = message.get('battery_voltage')
        if 'battery_remaining' in message: self.last_battery_remaining = message.get('battery_remaining')
        if 'signal_strength' in message: self.last_signal_strength = message.get('signal_strength')

        text = f'''
        Lat: {self.last_lat:.6f}
        Lon: {self.last_lon:.6f}
        Altitude: {self.last_alt:.2f} m
        Speed: {self.last_ground_speed:.2f} m/s
        Battery: {self.last_battery_voltage:.2f}V ({self.last_battery_remaining}%)
        Signal: {self.last_signal_strength}
        '''
        self.telemetry_dashboard.setText(text.strip())



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
        self.log_message("Shutting down...")
        self.video_thread.stop()
        self.telemetry_listener.stop()
        self.gimbal_udp_sender.close()
        self.ht_backend.save_known_faces()
        self.telemetry_listener.join() # Wait for the telemetry thread to finish
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    gui = DroneControlGUI()
    gui.show()
    # gui.start_server_task()

    with loop:
        loop.run_forever()