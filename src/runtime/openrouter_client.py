from typing import Any

from openai import OpenAI

from src.runtime.config import get_runtime_settings


class OpenRouterModelClient:
    """OpenRouter chat client with the response shape used by Shellmate skills."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        settings = get_runtime_settings()
        self._model = model or settings.openrouter_model

        if client is not None:
            self._client = client
            return

        api_key = (
            settings.openrouter_api_key.get_secret_value().strip()
            if settings.openrouter_api_key is not None
            else ""
        )
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY must be configured to use the chat model.")

        self._client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=api_key,
            max_retries=0,
        )

    def chat(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
        )
        if not response.choices:
            raise RuntimeError("OpenRouter returned an empty chat completion.")

        message = response.choices[0].message
        tool_calls = [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                },
            }
            for tool_call in (message.tool_calls or [])
        ]
        return {
            "message": {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": tool_calls,
            }
        }
