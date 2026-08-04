from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_title: str = "Chat-Based Linux Server Manager"
    api_version: str = "0.1.0"
    frontend_api_base_url: str = Field(
        default="http://localhost:8000/api/v1",
        description="Base URL for frontend to reach the backend.",
    )
    shellmate_api_key: str = Field(default="")
    cors_allowed_origins: str = Field(default="http://localhost:8501")
    ssh_command_timeout_seconds: int = Field(default=20, ge=1, le=300)
    ssh_key_storage_dir: Path = Field(default=Path("backend/data/keys"))
    ssh_key_max_size_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
    server_database_path: Path = Field(default=Path("backend/data/servers.db"))
    memory_database_path: Path = Field(default=Path("backend/data/memory.db"))
    historical_memory_path: Path = Field(default=Path("backend/data/chroma"))
    log_directory: Path = Field(default=Path("logs"))
    log_level: str = Field(default="INFO")
    log_file_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
