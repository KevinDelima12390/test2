# Human Tracking System v1.4

This document provides an overview of the Human Tracking System, a Ground Control Station (GCS) for professional drone operations.

**Version:** 1.4
**Date:** 2024-07-26

## Key Features

- **Unified Interface:** A single, dark-themed PyQt6 GUI for comprehensive drone control, live video monitoring, and human tracking.
- **Manual Gimbal Control:** Fine-tune the camera's view with joystick-style gimbal control.
- **Real-Time Telemetry & Mapping:** Displays live drone telemetry on an interactive map, including drone position, waypoints, and mission routes.
- **Facial Recognition:** Identifies and labels known individuals in the video feed.
- **External System Integration:**
  - **IBIS API:** Connects to the IBIS system to preload user data, including facial recognition profiles.
  - **WebSocket Alerts:** Listens for real-time emergency alerts to automate mission tasking.

---

## 1. System Architecture

The system consists of three main components:

1.  **Main GUI (`main_gui.py`):** The central application built with PyQt6. It integrates all modules into a user-friendly interface.
2.  **Backend (`human_tracker_backend.py`):** Powers the human detection, tracking, and facial recognition features using `torch` and `ultralytics`.
3.  **Mavlink Bridge (`mavlink_communicator.py`):** Manages communication with the drone via the MAVLink protocol, translating GUI commands into drone actions and relaying telemetry.

---

## 2. Core Functionalities

### 2.1. IBIS Integration

The GCS is designed to work seamlessly with the **IBIS (Integrated Biometric Identification System)**.

- **User Pre-loading:** On startup, the system connects to the IBIS REST API to fetch a list of registered users and their facial recognition encodings. This allows the system to immediately identify known individuals.
- **Emergency Alert System:** The GCS listens on a WebSocket for `emergency` messages broadcast from the IBIS server. When an alert is received, it automatically generates a waypoint on the map at the specified coordinates, allowing the operator to dispatch the drone to the location with a single click.

---

## 3. Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Install dependencies:**
    Ensure you have Python 3.10+ and pip.
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the application:**
    ```bash
    python main_gui.py
    ```

**Note on Models:** This application requires the `yolov9c.pt` and `face_detection_yunet_2023mar.onnx` models to be present in the correct locations (`yolov9c.pt` in the root and `face_detection_yunet_2023mar.onnx` in the `models` directory). These files are included in the repository.

---

## 4. API and Communication

### 4.1. IBIS API Credentials

The system uses the following hardcoded credentials to access the IBIS API.
- **User ID:** `Admin01`
- **Password:** `Delima12390`

### 4.2. WebSocket Endpoint

- **IBIS Alerts:** `ws://3.25.229.21:8000/ws/arc_engine`

This endpoint is used by the server to broadcast real-time messages, such as emergency alerts, which are then processed by the GCS.
