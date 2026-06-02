from fastapi import FastAPI
from app.api import sync
from app.core.config import settings
from app.core.database import engine, Base

# create db tables
Base.metadata.create_all(bind=engine)

# init FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# router: connects to sync endpoint
app.include_router(sync.router, prefix="/api/v1", tags=["Sync"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Oura Health Intellignece API"}