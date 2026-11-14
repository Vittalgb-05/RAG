"""Configuration settings for the RAG FastAPI application."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(env_prefix="RAG_", env_file=".env", extra="ignore")

    api_host: str = "127.0.0.1"
    api_port: int = 8000
    allow_non_loopback: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    serve_frontend: bool = False          # mount frontend/out at "/" (static export)
    persist_chat: bool = True
    store_originals: bool = False         # needed for Evidence Lens page images
    data_dir: Path = Path("data")
    log_dir: Path = Path("data/logs")
    log_level: str = "INFO"
