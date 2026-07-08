from fastapi import FastAPI
from app.api import sync
from app.core.config import settings
from app.core.database import engine, Base
from app.api import sync, chat
from fastapi.middleware.cors import CORSMiddleware

# create db tables
Base.metadata.create_all(bind=engine)

# init FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION
)

# set up origins for CORS
origins = [
    "http://localhost:5173"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# router: connects to sync endpoint and chat endpoint
app.include_router(sync.router, prefix="/api/v1", tags=["Sync"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the Oura Health Intellignece API"}