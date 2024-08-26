# dependencies.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from redis import Redis
import os
from enum import Enum

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/reservation')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

class UserRole(str, Enum):
    ADMIN = "admin"
    PROVIDER = "provider"
    PATIENT = "patient"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_redis_client():
    return redis_client