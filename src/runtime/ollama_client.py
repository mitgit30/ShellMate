from ollama import Client

from src.runtime.config import get_runtime_settings


class OllamaModelClient:
    def __init__(self) -> None:
        settings = get_runtime_settings()
        headers: dict[str, str] = {}
        if settings.ollama_api_key:
            headers["Authorization"] = f"Bearer {settings.ollama_api_key}"

        self._client = Client(host=settings.ollama_base_url, headers=headers or None)
        self._model = settings.ollama_model

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat(
            model=self._model,
            messages=messages,
            tools=tools,
        )
        return response.model_dump()
