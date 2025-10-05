# IBIS Database System (Integrated Biometric & Incident System)

This project provides a local backend API and database for user registration with facial recognition, secure login, and emergency event management. It supports full offline capability using SQLite and integrates with an ARC Engine (drone system) via WebSockets for emergency alerts.

## Features

-   **User Management:** Register users with unique IDs, names, passwords, and facial images.
-   **Secure Authentication:** User login with password hashing (bcrypt) and JWT token generation.
-   **Facial Recognition:** Extracts and stores face encodings for biometric identification.
-   **Emergency Alerts:** Log emergency events with GPS coordinates and trigger real-time notifications to an ARC Engine via WebSocket.
-   **Event History:** Retrieve a user's emergency event history.
-   **Offline Capability:** Uses a local SQLite database (`ibis.db`).

## Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd ibis_database_system
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## How to Run

### 1. Start the FastAPI Server

Navigate to the `ibis_database_system` directory and run the server using Uvicorn:

```bash
uvicorn ibis_api:app --reload
```

The API will be accessible at `http://127.0.0.1:8000`.

### 2. Run the Test Client (Optional)

In a separate terminal, you can run the `test_client.py` script to simulate user registration, login, emergency triggers, and event fetching:

```bash
python test_client.py
```

**Note:** The `test_client.py` will attempt to create a dummy `test_image.jpg` if it doesn't exist. Ensure you have `Pillow` installed (`pip install Pillow`) for this functionality.

### 3. Connect ARC Engine WebSocket Client (Optional)

To test the WebSocket notification for emergency events, you can run the `arc_engine_websocket_client` function from `test_client.py` in a separate process or terminal:

```bash
python -c "import asyncio, test_client; asyncio.run(test_client.arc_engine_websocket_client())"
```

## API Endpoints

### `POST /register`
Registers a new user with facial image.

**Request (multipart/form-data):**
-   `user_id`: string (e.g., `john123`)
-   `name`: string (e.g., `John Doe`)
-   `password`: string (e.g., `securepassword`)
-   `image`: file (JPEG, PNG, etc.)

**Example (using `curl`):**
```bash
curl -X POST "http://127.0.0.1:8000/register" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "user_id=testuser1" \
  -F "name=Test User" \
  -F "password=testpassword" \
  -F "image=@./test_image.jpg;type=image/jpeg"
```

### `POST /login`
Authenticates a user and returns a JWT token.

**Request (application/json):**
```json
{
  "user_id": "testuser1",
  "password": "testpassword"
}
```

**Example (using `curl`):**
```bash
curl -X POST "http://127.0.0.1:8000/login" \
  -H "accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"testuser1\", \"password\": \"testpassword\"}"
```

### `POST /emergency`
Logs an emergency event and notifies the ARC Engine.
Requires JWT authentication.

**Request (application/json):**
```json
{
  "user_id": "testuser1",
  "latitude": 3.12121,
  "longitude": 101.65432
}
```

**Example (using `curl` after obtaining a token):**
```bash
TOKEN="<your_jwt_token_here>"
curl -X POST "http://127.0.0.1:8000/emergency" \
  -H "accept: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"testuser1\", \"latitude\": 3.12121, \"longitude\": 101.65432}"
```

### `GET /events/{user_id}`
Fetches emergency history for a given user.
Requires JWT authentication.

**Example (using `curl` after obtaining a token):**
```bash
TOKEN="<your_jwt_token_here>"
curl -X GET "http://127.0.0.1:8000/events/testuser1" \
  -H "accept: application/json" \
  -H "Authorization: Bearer $TOKEN"
```

### `WebSocket /ws/arc_engine`
ARC Engine clients can connect to this WebSocket endpoint to receive real-time emergency notifications.

**Notification Message Format:**
```json
{
  "type": "emergency",
  "user_id": "john123",
  "lat": 3.12121,
  "lon": 101.65432
}
```

## Security Notes

-   Passwords are hashed using bcrypt.
-   JWT tokens are used for API authentication.
-   Face encodings are stored as binary data.
-   The SQLite database file (`ibis.db`) is stored locally.

## Offline Capability

The system is designed to work fully offline, relying solely on the local SQLite database for data storage.
