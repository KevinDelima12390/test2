from sqlalchemy import create_engine, Column, Integer, String, Float, BLOB, TIMESTAMP, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# Use environment variable for database URL, with a default for local development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ibis.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, unique=True, not_null=True, index=True)
    name = Column(String, not_null=True)
    password_hash = Column(String, not_null=True)
    face_encoding = Column(BLOB)
    image_path = Column(String)
    created_at = Column(TIMESTAMP, default=datetime.datetime.utcnow)

class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, not_null=True, index=True)
    latitude = Column(Float, not_null=True)
    longitude = Column(Float, not_null=True)
    triggered_at = Column(TIMESTAMP, default=datetime.datetime.utcnow)
    status = Column(String, default="pending")

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

