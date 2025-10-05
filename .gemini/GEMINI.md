## Gemini Added Memories
- The AI Human Tracking System is currently at a stable and fully functional checkpoint (Version 1.4), using a pure OpenCV GUI for video display and controls.

## Recent Development Summary (yolo_human_tracker)

### Resolved Issues:
-   **`RuntimeError: no running event loop`**: Resolved by implementing a dedicated background thread for the `asyncio` event loop using `threading` in `main_gui.py`.
-   **`js: Uncaught ReferenceError: L is not defined`**: Resolved by using locally downloaded Leaflet files and ensuring correct script loading order in `map.html`, and by explicitly setting `QWebEngineSettings` and `baseUrl` in `main_gui.py`.
-   **"The truth value of an array with more than one element is ambiguous."**: Resolved by explicitly checking for `None` and empty encodings in `human_tracker_backend.py`.
-   **`401 Unauthorized` for `/users_with_faces`**: Resolved by switching to direct `ibis.db` file access for user data, removing API-based authentication for this purpose.
-   **`SyntaxError: f-string: unmatched '('`**: Resolved by correcting nested quotes in `log_message` function in `main_gui.py`.
-   **`AttributeError: 'builtin_function_or_method' object has no attribute 'connect'` (for `javaScriptConsoleMessage`)**: Resolved by implementing a `CustomWebEnginePage` subclass to override `javaScriptConsoleMessage` directly.
-   **`NameError: name 'QWebEngineSettings' is not defined`**: Resolved by adding `from PyQt6.QtWebEngineCore import QWebEngineSettings` to `main_gui.py`.
-   **Map Not Visible / `QWebEngineView` Malfunction**: Resolved by implementing a Flask-based web server (`map_server.py`) serving a Leaflet map (`templates/map.html`) in an external browser, completely bypassing `QWebEngineView`. Drone position updates, waypoint display, and flight path visualization are now handled via HTTP requests to the Flask server.
-   **Map Coordinate Updates**: Resolved by correcting the telemetry simulation in `main_gui.py` to directly emit messages, ensuring `update_map_position` is called and sends updates to the Flask server.

### Persistent Issues:
-   **Flight Paths Not Drawing on Map**: The flight paths are not being drawn on the map in the web browser, even though waypoints are being added and cleared on the Flask server.
-   **Camera Initialization Failure**: `OpenCV: camera failed to properly initialize!` errors are occurring, preventing the video feed from working. This is likely due to incorrect camera index, permissions, or OpenCV installation issues.
-   **IBIS API 401 Unauthorized for `/emergency`**: The IBIS API is returning a 401 Unauthorized error for the `/emergency` endpoint.
-   **Face Detection Display**: The GUI is not displaying the name of the detected person when a face is detected.

### Current Plan:
-   **Map Display (Flight Paths)**: Debug and fix the issue with flight paths not drawing on the Leaflet map in the browser. This will involve examining browser console logs.
-   **Face Detection Display**: Implement the display of detected person's name in the GUI.
-   **Camera Initialization**: Investigate and fix the camera initialization failures.
-   **IBIS API `/emergency` 401**: Investigate and fix the 401 Unauthorized error for the `/emergency` endpoint.