# System Documentation: AI Human Tracking and Emergency Response System

## 1. System Overview

This project consists of two main, independent but interconnected systems:

1.  **IBIS Database System:** A backend service for managing user identities, including biometric facial data, and logging emergency events.
2.  **YOLO Human Tracker System:** A desktop application that serves as a Ground Control Station (GCS) for a drone. It provides a graphical user interface for monitoring a video feed, tracking humans using AI, and controlling a drone.

The two systems work together to create a comprehensive solution for emergency response. The IBIS system provides the identity management and emergency logging, while the YOLO Human Tracker provides the real-world tracking and response capabilities.

---

## 2. IBIS Database System (`ibis_database_system/`)

### Purpose

The IBIS (Integrated Biometric & Incident System) is a backend API and database that provides the following services:

*   User registration with facial recognition data.
*   Secure user authentication.
*   A system for logging emergency events with GPS coordinates.
*   Real-time notification of emergency events to connected clients (like the YOLO Human Tracker).

### Components

*   **`ibis_api.py`:** The core of the system. It's a FastAPI application that exposes a RESTful API for all the system's functionalities. It also manages a WebSocket connection for real-time communication.
*   **`database.py`:** Defines the database schema using SQLAlchemy. It creates two tables: `users` (to store user information, including hashed passwords and facial encodings) and `emergency_events` (to log emergencies).
*   **`security.py`:** Handles all security-related aspects, including password hashing (using bcrypt) and the creation and verification of JWT (JSON Web Tokens) for authenticating API requests.
*   **`ibis.db`:** A SQLite database file that stores all the system's data. This allows the system to be self-contained and run offline.
*   **`uploads/`:** A directory where images uploaded during user registration are stored.

### Functionality

*   **User Registration (`/register`):** A user can register with a user ID, name, password, and a picture of their face. The system processes the image to extract a facial encoding (a mathematical representation of the face) and stores it in the database along with the other user data.
*   **User Login (`/login`):** A user can log in with their user ID and password. If the credentials are correct, the system returns a JWT token that can be used to access protected API endpoints.
*   **Emergency Trigger (`/emergency`):** An authenticated user can trigger an emergency event by providing their user ID and their current latitude and longitude. This event is saved to the database.
*   **Emergency Notification (`/ws/arc_engine`):** When an emergency is triggered, the system immediately sends a notification to all clients connected to its WebSocket endpoint. This notification includes the user ID and the location of the emergency.
*   **Event History (`/events/{user_id}`):** An authenticated user can retrieve a history of their past emergency events.

### Communication

*   **REST API:** The primary way to interact with the system is through its REST API, which is served on `http://127.0.0.1:8000`.
*   **WebSockets:** The system provides a WebSocket endpoint (`ws://127.0.0.1:8000/ws/arc_engine`) for real-time communication of emergency events.

---

## 3. YOLO Human Tracker System (`yolo_human_tracker/`)

### Purpose

The YOLO Human Tracker is a desktop application that acts as a Ground Control Station (GCS) for a drone. It's designed to provide a user with a comprehensive view of a situation and allow them to control a drone to respond to events.

### Components

*   **`main_gui.py`:** The main entry point and the core of the application. It creates the PyQt6 GUI, initializes all the backend modules, and handles the interactions between them.
*   **`map_server.py`:** A small Flask web server that serves an interactive Leaflet map. This map is displayed in a web browser and is updated in real-time by the `main_gui.py`.
*   **`drone_module/`:** A directory containing all the backend logic for the GCS.
    *   **`human_tracker_backend.py`:** The AI core of the system. It uses a YOLOv8 model to detect humans in the video feed and the `face_recognition` library to identify them.
    *   **`video_stream.py`:** Captures the video feed from a camera (specifically an RTSP stream from an IP camera) in a separate thread and passes the frames to the `human_tracker_backend.py` for processing.
    *   **`websocket_bridge.py`:** Manages WebSocket communications. It starts a server for internal communication (e.g., with a drone simulator) and connects as a client to the IBIS system to receive emergency alerts.
    *   **`mavlink_communicator.py`:** Sends commands to a MAVLink-compatible drone (e.g., arm, disarm, takeoff, land, control gimbal).
    *   **`drone_telemetry.py`:** Listens for incoming telemetry data from a MAVLink drone and passes it to the GUI for display.
    *   **`waypoint_deployer.py`:** A GUI widget for managing and displaying waypoints, which are generated from emergency alerts.

### Functionality

*   **GUI:** A dark-themed, multi-panel GUI that displays the video feed, map, drone status, telemetry, logs, and controls.
*   **Video Processing:** Captures a live video stream and uses the `human_tracker_backend.py` to perform human detection, tracking, and facial recognition. The processed video, with bounding boxes and labels, is displayed in the GUI.
*   **Human Tracking:** Uses the YOLOv8 object detection model to find humans in the video feed and tracks them from frame to frame.
*   **Facial Recognition:** When a human is tracked, the system attempts to detect their face and compare it to a database of known faces. This database is populated by directly reading from the IBIS system's `ibis.db` file.
*   **Drone Control:** The user can send commands to the drone, such as arming/disarming, setting flight modes, and controlling the gimbal.
*   **Map Display:** An interactive map is displayed in a web browser. The map shows the drone's current position and any waypoints. The drone's position is updated in real-time.

### Communication

*   **MAVLink:** The system communicates with a real drone using the MAVLink protocol over UDP. It sends commands on one port and listens for telemetry on another.
*   **WebSockets:**
    *   It connects as a client to the IBIS system's WebSocket to receive emergency alerts.
    *   It runs its own WebSocket server to allow other components (like a drone simulator) to connect to it.
*   **HTTP:** It communicates with the `map_server.py` via HTTP requests to update the drone's position and waypoints on the map.
*   **Direct Database Access:** It directly reads the `ibis.db` SQLite file to get user and face encoding data. It also monitors the `uploads` directory for new images.

---

## 4. System Interaction

The two systems are designed to work together in an emergency response scenario:

1.  **User Registration (IBIS):** A user registers with the IBIS system, providing their name and a photo. The IBIS system stores this information and the user's facial encoding in its database.
2.  **Face Loading (YOLO Tracker):** The YOLO Human Tracker application starts. It directly accesses the `ibis.db` file and loads the facial encodings of all registered users into its `human_tracker_backend.py`.
3.  **Emergency (IBIS):** A user is in distress. They use a (hypothetical) client application to log into the IBIS system and trigger an emergency, sending their GPS coordinates.
4.  **Notification (IBIS -> YOLO Tracker):** The IBIS system saves the emergency event and immediately broadcasts a WebSocket message containing the user's ID and GPS coordinates.
5.  **Alert (YOLO Tracker):** The YOLO Human Tracker's `websocket_bridge.py` receives the emergency notification.
6.  **Waypoint (YOLO Tracker):** The `main_gui.py` receives the notification data, and adds a new waypoint to the `waypoint_deployer` and the map, showing the location of the emergency.
7.  **Response (YOLO Tracker):** The drone operator sees the new waypoint on the map and can command the drone to fly to that location.
8.  **Identification (YOLO Tracker):** As the drone's camera streams video from the emergency location, the `human_tracker_backend.py` processes the feed. If it detects the person who triggered the emergency, it uses facial recognition to identify them by name and displays this information in the GUI.

---

## 5. Data Flow Diagram (Text-based)

```
+----------------------+      +------------------------+      +-----------------------+
| User's Mobile Device |----->|  IBIS Database System  |<---->|      ibis.db        |
| (Hypothetical)       |      | (FastAPI, SQLAlchemy)  |      | (SQLite Database)     |
+----------------------+      +------------------------+      +-----------------------+
     | (REST API:      ^           | (WebSocket:             ^
     | /emergency)     |           | emergency alert)        | (Direct file read)
     v                 |           v                         |
+----------------------+<----------+-------------------------+
| YOLO Human Tracker   |
| (PyQt6 GCS)          |
|                      |
|  +-----------------+ |      +------------------------+
|  |   main_gui.py   | |----->|     map_server.py      |
|  +-----------------+ |<-----| (Flask, Leaflet Map)   |
|  | websocket_bridge| | (HTTP)|                      |
|  | human_tracker   | |      +------------------------+
|  | mavlink_comm    | |
|  | drone_telemetry | |
|  +-----------------+ |
+----------------------+
     |           ^
     | (MAVLink  | (MAVLink
     | commands) | telemetry)
     v           |
+----------------------+
|       Drone          |
| (or Simulator)       |
+----------------------+
```