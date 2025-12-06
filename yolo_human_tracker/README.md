# ARC_ENGIN with Human Tracking

This is a Python-based Ground Control Station (GCS) for drones, featuring a dark-themed PyQt6 GUI, WebSocket communication, an interactive map display, and integrated AI-powered human tracking.

## Features

- **Integrated Control:** A single interface for both drone control and human tracking.
- **Live Video Feed:** Real-time video from a webcam, with AI-powered human detection and tracking.
- **Facial Recognition:** Identify and name tracked individuals.
- **Drone Telemetry:** Real-time display of drone telemetry data via WebSocket.
- **Interactive Map:** Live drone tracking and waypoint management on an interactive Leaflet map.
- **Gimbal Control:** Joystick-style control for the drone's gimbal.
- **Waypoint Management:** Add, edit, and delete waypoints, and fly missions (simulated).

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install the dependencies:**
   Make sure you have the latest `requirements.txt` and run:
   ```bash
   pip install -r requirements.txt
   ```

## How to Run

1. **Start the application:**
   ```bash
   python main_gui.py
   ```

The application will start, and you will be prompted to select a camera for the human tracking system.

## Connecting a Drone

To see live drone telemetry, you need to connect a drone or a drone simulator that sends telemetry data in the expected JSON format over a WebSocket connection to `ws://localhost:8765`.

### Message Format

The JSON packets sent to the GUI should follow this format:

**Telemetry (Drone → GUI):**
```json
{
  "type": "telemetry",
  "drone_id": "AERIS-01",
  "timestamp": 1699999999,
  "telemetry": {
    "lat": 3.12345,
    "lon": 101.65432,
    "altitude_m": 82.5,
    "speed_kmh": 18.2,
    "battery_pct": 78,
    "heading_deg": 237,
    "flight_time_s": 320
  },
  "gimbal": { "pan_deg": 10, "tilt_deg": -5 }
}
```

**Commands (GUI → Drone):**
The GUI sends commands in this format:
```json
{
  "type":"command",
  "command":"gimbal",
  "drone_id":"AERIS-01",
  "payload": {"pan_deg": 15, "tilt_deg": -10}
}
```

### MAVLink Integration

To connect a real drone using MAVLink, you will need to create a MAVLink-to-WebSocket bridge. This script will:
1.  Connect to your drone via MAVLink.
2.  Convert MAVLink messages to the JSON format expected by the GUI.
3.  Forward the JSON packets to the GUI over WebSocket.
4.  Listen for commands from the GUI, convert them to MAVLink commands, and send them to the drone.
