from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    openrouter_model: str = Field(default="nvidia/nemotron-3-ultra-550b-a55b:free")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1")
    openrouter_api_key: SecretStr | None = Field(default=None, repr=False)
    ollama_base_url: str = Field(default="https://ollama.com")
    ollama_api_key: SecretStr | None = Field(default=None, repr=False)
    ollama_embedding_model: str = Field(default="nomic-embed-text")
    agent_max_turns: int = Field(default=10, ge=1, le=10)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings()
