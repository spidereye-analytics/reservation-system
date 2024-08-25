from fastapi import FastAPI
from fastapi_sqlalchemy import DBSessionMiddleware
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
import os

redis_client = Redis(host='redis', port=6379, decode_responses=True)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/reservation')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def create_app() -> FastAPI:
    app = FastAPI()

    app.add_middleware(DBSessionMiddleware, db_url=DATABASE_URL)

    from .routes import router as main_router
    app.include_router(main_router)

    return app
