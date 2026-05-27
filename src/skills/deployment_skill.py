from collections.abc import Iterator

from src.deployments.engine import DeploymentEngine
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext


class DeploymentSkill(BaseSkill):
    id = "deployment"
    name = "Deployment Engine"
    description = (
        "Handles Docker deployment requests with a conversational front layer and a "
        "structured, approval-based execution pipeline."
    )

    def __init__(self, deployment_engine: DeploymentEngine, model_client: OllamaModelClient) -> None:
        self._deployment_engine = deployment_engine
        self._model_client = model_client

    def execute(self, context: SkillContext) -> Iterator[dict]:
        if self._should_answer_conversationally(context.user_message):
            yield {
                "type": "step_started",
                "step": "deployment_conversation",
                "detail": "Answering the deployment question conversationally before any rollout starts.",
            }
            reply = self._build_conversational_reply(context)
            yield {
                "type": "step_completed",
                "step": "deployment_conversation",
                "detail": "Shared a deployment-focused answer without starting the execution pipeline.",
            }
            for token in self._chunk_text(reply):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        yield {
            "type": "step_started",
            "step": "deployment_mode",
            "detail": "Switched from conversational mode to structured deployment mode.",
        }
        yield from self._deployment_engine.stream(context)

    def _build_conversational_reply(self, context: SkillContext) -> str:
        system_prompt = (
            "You are ShellMate's deployment assistant.\n"
            "The user is asking about deployments in a conversational way, not asking you to start a rollout yet.\n"
            "Respond in a warm, clear, user-friendly style.\n"
            "Do not say that validation failed or that Docker is missing unless the user explicitly asked you to check the current server.\n"
            "If the user is asking about capability, explain what you can do.\n"
            "If the user is asking how deployment would work, explain the flow simply.\n"
            "If the user is asking about installing Docker, explain the safe next step and mention that you can help check the server first.\n"
            "Keep the answer concise, practical, and non-technical unless the user asks for more detail."
        )
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                *context.history[-6:],
                {"role": "user", "content": context.user_message},
            ],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        return content.strip() or (
            "Yes, I can help with Docker-based deployments. If you want, I can first check the server, "
            "confirm whether Docker is available, and then prepare a safe deployment plan before making any changes."
        )

    @staticmethod
    def _should_answer_conversationally(user_message: str) -> bool:
        lowered = user_message.lower()
        conversational_terms = (
            "what can you do",
            "can you",
            "how do you",
            "how would you",
            "how to",
            "help me understand",
            "is it possible",
            "do you support",
            "install docker",
            "docker install",
        )
        action_terms = (
            "deploy ",
            "deployment of",
            "containerize ",
            "containerise ",
            "build and run",
            "docker compose up",
            "approve deployment",
            "cancel deployment",
        )
        asks_current_server_check = (
            "on this server" in lowered
            or "on the server" in lowered
            or "check whether" in lowered
            or "is docker installed" in lowered
        )
        if asks_current_server_check:
            return False
        if any(term in lowered for term in action_terms):
            return False
        return any(term in lowered for term in conversational_terms) or lowered.endswith("?")

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix
