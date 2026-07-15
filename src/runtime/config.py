from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    ollama_model: str = Field(default="gpt-oss:120b-cloud")
    ollama_base_url: str = Field(default="http://127.0.0.1:11434")
    ollama_api_key: str | None = None
    agent_max_turns: int = Field(default=10, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings()
