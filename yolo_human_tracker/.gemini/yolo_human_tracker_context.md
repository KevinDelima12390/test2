# Yolo Human Tracker Architecture Summary and New Feature Context

This document provides a summary of the Yolo Human Tracker application's architecture and outlines the context for implementing new "Select and Follow" functionalities for the drone's gimbal and the drone itself.

## Current Architecture Summary

The Yolo Human Tracker is a multi-component Python application designed to detect and track humans, integrate with drone systems via MAVLink, and provide a graphical user interface (GUI) for monitoring and control.

### Key Components:

1.  **`video_stream.py`**:
    *   **Purpose**: Manages the acquisition of video frames from various sources (e.g., local camera, RTSP streams from drones).
    *   **Operation**: Runs in a separate thread to ensure continuous frame capture without freezing the main GUI, emitting frames for processing.

2.  **`human_tracker_backend.py`**:
    *   **Purpose**: The core intelligence for object detection, tracking, and face recognition.
    *   **Object Detection**: Utilizes the `ultralytics.YOLO` model (`yolov8n.pt`) to identify "person" objects within each video frame.
    *   **Human Tracking**: Maintains `self.tracked_objects` to assign and manage unique IDs for detected individuals across consecutive frames, likely employing centroid-based tracking.
    *   **Face Recognition**: Incorporates the `face_recognition` library to identify known faces.
        *   Loads existing known face encodings from `known_faces.pkl`.
        *   Supports importing user-specific face data from an external IBIS API via the `import_ibis_faces` method (recently implemented).
        *   Stores face encodings and associated user details (name, image).
    *   **Low Light Enhancement**: Offers a toggleable feature using OpenCV's CLAHE (Contrast Limited Adaptive Histogram Equalization) for improved visibility in challenging lighting conditions.
    *   **Visual Overlays**: Renders bounding boxes, person IDs, recognized names, and face detection rectangles directly onto the video frames.
    *   **State Management**: Includes `self.paused` for controlling video processing flow, `self.face_recognition_enabled`, and `self.low_light_enhancement_enabled` for feature toggles.

3.  **`mavlink_communicator.py`**:
    *   **Purpose**: Establishes and manages the MAVLink communication link with a drone (e.g., over UDP).
    *   **Functionality**: Responsible for sending control commands to the drone and receiving telemetry data.

4.  **`drone_telemetry.py`**:
    *   **Purpose**: Listens for and processes incoming MAVLink telemetry messages from the connected drone.
    *   **Data Provided**: Extracts critical drone data such as GPS position, altitude, attitude (pitch, roll, yaw), and potentially battery status.

5.  **`gimbal_control.py`**:
    *   **Purpose**: Designed to translate target positions into gimbal control commands.
    *   **Functionality**: Will likely calculate required gimbal pitch and yaw adjustments based on a target (e.g., a tracked human's position in the video frame) and send these commands via `mavlink_communicator.py` to physically control the drone's camera.

6.  **`position_tracker.py`**:
    *   **Purpose**: To correlate drone telemetry with object tracking data to determine real-world positions.
    *   **Functionality**: Expected to use the drone's GPS data and the relative position of a tracked human to estimate the human's absolute geographic coordinates.

7.  **`map_server.py` & `templates/map.html`**:
    *   **Purpose**: Provides a web-based map interface.
    *   **Operation**: A Flask application that serves `map.html` (which likely uses a JavaScript mapping library like Leaflet or OpenLayers). It offers API endpoints (e.g., `/coords`) to receive and display real-time positions of the drone and potentially tracked humans on the map.

8.  **`main_gui.py`**:
    *   **Purpose**: The main application entry point and user interface, built with PyQt6.
    *   **Orchestration**: Initializes and connects instances of `VideoStream`, `HumanTrackerBackend`, `MAVLinkCommunicator`, etc.
    *   **Display**: Shows the live video feed enhanced with overlays from the tracking backend.
    *   **User Interaction**: Provides controls for toggling face recognition and low-light enhancement. It integrates with the IBIS API to fetch user data for facial recognition.

## Context for New "Select and Follow" Features

The new features require enhancing the interaction between the GUI, the tracking backend, and the drone control modules.

### 1. Selecting a Tracked Person:

*   **GUI (`main_gui.py`)**: Need to implement a mechanism for users to select one of the detected/tracked persons on the video feed. This could involve:
    *   Clicking on a bounding box.
    *   A dropdown/list of tracked person IDs.
    *   This selection will need to communicate the `person_id` of the chosen individual to the backend.

### 2. Gimbal Follow Mode:

*   **Trigger**: A new button in `main_gui.py` (e.g., "Gimbal Follow").
*   **Logic Flow**:
    1.  User selects a tracked person in the GUI.
    2.  User clicks "Gimbal Follow".
    3.  The GUI passes the `person_id` of the selected target to the `human_tracker_backend` or a new controller class.
    4.  The `human_tracker_backend` will need to continuously provide the screen coordinates/bounding box of the selected `person_id`.
    5.  `gimbal_control.py` will receive these screen coordinates.
    6.  `gimbal_control.py` will calculate the necessary gimbal pitch and yaw adjustments to keep the target centered (or within a target area) in the camera's view.
    7.  These adjustments will be sent as MAVLink commands via `mavlink_communicator.py` to the drone's gimbal.

### 3. Drone Follow Mode:

*   **Trigger**: A new button in `main_gui.py` (e.g., "Drone Follow").
*   **Logic Flow**:
    1.  User selects a tracked person in the GUI.
    2.  User clicks "Drone Follow".
    3.  The GUI passes the `person_id` to a higher-level control module.
    4.  `position_tracker.py` will be crucial here: it needs to continuously estimate the real-world GPS coordinates of the selected tracked person, potentially relative to the drone's current position and heading.
    5.  These target GPS coordinates, along with desired follow distance/altitude, will be sent as navigation commands to the drone.
    6.  This might involve generating and updating waypoints dynamically or sending velocity commands directly via `mavlink_communicator.py`. The `waypoint_deployer.py` module (present in `drone_module`) is likely intended for this purpose.
    7.  The drone will then use its flight controller to autonomously navigate to and maintain the specified follow parameters relative to the target.

### Considerations:

*   **State Management**: How to manage the active "follow" target, and toggle between gimbal and drone follow modes (or turn them off).
*   **Error Handling**: What happens if the tracked person is lost, or drone communication is interrupted?
*   **User Feedback**: Providing visual feedback in the GUI about which person is selected, if a follow mode is active, and the drone's status.
*   **Safety**: Implementing safety limits for drone follow (e.g., maximum distance, minimum altitude, geofencing).
*   **Existing `waypoint_deployer.py`**: This module will be central to implementing drone follow, likely handling the conversion of target GPS into MAVLink waypoint or movement commands. It needs further investigation to understand its current capabilities.
