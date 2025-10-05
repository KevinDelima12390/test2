from fastapi import Depends, FastAPI, HTTPException, status, File, UploadFile, Form, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import shutil
import pickle
import face_recognition
import numpy as np
import os
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import List
import json
from fastapi.middleware.cors import CORSMiddleware

import database
import security
from database import SessionLocal, engine, User, EmergencyEvent

database.create_db_and_tables()

app = FastAPI()

origins = [
    "http://localhost:5173",  # Your Vite frontend development server
    "http://127.0.0.1:5173",  # Another common address for Vite
    # Add any other origins where your frontend might be hosted (e.g., production domain)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,        # List of allowed origins
    allow_credentials=True,       # Allow cookies to be included in requests
    allow_methods=["*"],          # Allow all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],          # Allow all headers in the request
)

# OAuth2PasswordBearer for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# Pydantic Models
class UserLogin(BaseModel):
    user_id: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class EmergencyCreate(BaseModel):
    user_id: str
    latitude: float
    longitude: float

class EmergencyEventResponse(BaseModel):
    id: int
    user_id: str
    latitude: float
    longitude: float
    triggered_at: datetime
    status: str

    class Config:
        orm_mode = True

# WebSocket Manager for ARC Engine
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to get current user from token
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = security.verify_token(token, credentials_exception)
    user = db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise credentials_exception
    return user

@app.get("/")
def read_root():
    return {"message": "Welcome to the IBIS Database API"}

@app.post("/register")
def register_user(db: Session = Depends(get_db), user_id: str = Form(...), name: str = Form(...), password: str = Form(...), image: UploadFile = File(...)):
    db_user = db.query(User).filter(User.user_id == user_id).first()
    if db_user:
        raise HTTPException(status_code=400, detail="User ID already registered")

    # Save image
    uploads_dir = "uploads"
    os.makedirs(uploads_dir, exist_ok=True)
    image_path = os.path.join(uploads_dir, image.filename)
    with open(image_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)

    # Face encoding
    try:
        image_for_encoding = face_recognition.load_image_file(image_path)
        face_encodings = face_recognition.face_encodings(image_for_encoding)
        if not face_encodings:
            raise HTTPException(status_code=400, detail="No face found in the image.")
        face_encoding = pickle.dumps(face_encodings[0])
    except Exception as e:
        os.remove(image_path) # Clean up image if encoding fails
        raise HTTPException(status_code=500, detail=f"Could not process image: {e}")

    hashed_password = security.get_password_hash(password)

    new_user = User(
        user_id=user_id,
        name=name,
        password_hash=hashed_password,
        face_encoding=face_encoding,
        image_path=image_path
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "ok", "message": "User registered successfully"}

@app.post("/login", response_model=Token)
async def login_for_access_token(form_data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == form_data.user_id).first()
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.user_id}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/emergency", status_code=status.HTTP_202_ACCEPTED)
async def trigger_emergency(
    emergency_data: EmergencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure the user_id in the payload matches the authenticated user
    if current_user.user_id != emergency_data.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")

    # Save emergency event to DB
    new_event = EmergencyEvent(
        user_id=emergency_data.user_id,
        latitude=emergency_data.latitude,
        longitude=emergency_data.longitude,
        status="pending"
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)

    # Notify ARC Engine via WebSocket
    notification_message = {
        "type": "emergency",
        "user_id": emergency_data.user_id,
        "lat": emergency_data.latitude,
        "lon": emergency_data.longitude
    }
    await manager.broadcast(json.dumps(notification_message))

    return {"status": "mission_triggered"}

@app.put("/emergency/status/{event_id}")
async def update_emergency_status(
    event_id: int,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Requires authentication
):
    event = db.query(EmergencyEvent).filter(EmergencyEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Emergency event not found")
    
    # Optional: Add authorization check if only the user who triggered it can update
    # if event.user_id != current_user.user_id:
    #     raise HTTPException(status_code=403, detail="Not authorized to update this event")

    event.status = status
    db.commit()
    db.refresh(event)
    return {"message": f"Emergency event {event_id} status updated to {status}", "event": event}

@app.websocket("/ws/arc_engine")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, or handle incoming messages from ARC Engine if any
            # For now, just receive to keep the connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/events/{user_id}", response_model=List[EmergencyEventResponse])
async def get_emergency_events(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Ensure the user_id in the path matches the authenticated user
    if current_user.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User ID mismatch")

    events = db.query(EmergencyEvent).filter(EmergencyEvent.user_id == user_id).all()
    return events
