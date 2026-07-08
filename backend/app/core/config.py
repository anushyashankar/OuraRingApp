from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Oura Health Intelligence"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"

    OURA_ACCESS_TOKEN: str
    GOOGLE_API_KEY: str

    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/oura_db"
    SAMPLE_DATABASE_URL: str = "sqlite:///./sample_oura.db"
    BASELINE_WINDOW_DAYS: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

# singleton instance
settings = Settings() 