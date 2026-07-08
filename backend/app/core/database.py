from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings
from fastapi import Request
from typing import Optional

# engine: central connection point to PostgreSQL DB
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)
sample_engine = create_engine(
    settings.SAMPLE_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# session factory: for creating new database sessions for each request
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SampleSessionLocal = sessionmaker(bind=sample_engine)

# base: for all Tables to inherit from
class Base(DeclarativeBase):
    pass

# FastAPI dependency: FastAPI will call get_db, give the route a database session, and then
# automatically close the connection when the request is finished—even if the 
# request crashed -- prevents leaking connections.
# helper func for FastAPI to inject DB session into routes
def get_db(request: Request):
    use_sample = request.headers.get("X-Use-Sample") == "true"

    if use_sample:
        db = SampleSessionLocal()
    else:
        db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()