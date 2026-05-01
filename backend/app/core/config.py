from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_title: str = "Chat-Based Linux Server Manager"
    api_version: str = "0.1.0"
    frontend_api_base_url: str = Field(
        default="http://localhost:8000/api/v1",
        description="Base URL used by the Streamlit frontend to reach the backend.",
    )
    ssh_command_timeout_seconds: int = Field(default=20, ge=1, le=300)
    ssh_key_storage_dir: Path = Field(default=Path("backend/data/keys"))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
