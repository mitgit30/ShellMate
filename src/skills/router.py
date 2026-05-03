import json

from src.runtime.models import SkillRouteDecision
from src.runtime.ollama_client import OllamaModelClient
from src.skills.registry import SkillRegistry


class SkillRouter:
    def __init__(self, model_client: OllamaModelClient, skill_registry: SkillRegistry) -> None:
        self._model_client = model_client
        self._skill_registry = skill_registry

    def route(self, user_message: str, history: list[dict]) -> SkillRouteDecision:
        prompt = (
            "You are a skill router for a Linux server management agent.\n"
            "Choose the single best skill for the user's intent.\n"
            "Base the decision on what the user is trying to accomplish on the connected Linux server.\n"
            "Do not describe assistant behavior, UI behavior, or generic troubleshooting unless the user explicitly asked about them.\n"
            "Return JSON only with keys: skill_id, reason.\n"
            "The reason must be short, concrete, and focused on the user's actual server task.\n\n"
            "Available skills:\n"
            f"{self._skill_registry.routing_prompt()}\n"
        )
        messages = [
            {"role": "system", "content": prompt},
            *history[-6:],
            {"role": "user", "content": user_message},
        ]
        response = self._model_client.chat(messages=messages, tools=[])
        assistant_message = response.get("message", {})
        content = assistant_message.get("content", "") or ""

        try:
            payload = json.loads(content)
            return SkillRouteDecision(
                skill_id=str(payload["skill_id"]),
                reason=str(payload.get("reason", "Selected by the router.")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            default_skill_id = self._skill_registry.default_skill_id()
            return SkillRouteDecision(
                skill_id=default_skill_id,
                reason="Router fallback selected the default SSH skill.",
            )
