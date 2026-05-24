import json
from collections.abc import Iterator

from src.runtime.config import get_runtime_settings
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext
from src.tools.docker_tools import DockerTool


class DockerSkill(BaseSkill):
    id = "docker"
    name = "Docker Skill"
    description = "Manage Docker containers, images, and deployments on a server."

    def __init__(self, model_client: OllamaModelClient, docker_tool: DockerTool):
        self._model_client = model_client
        self._docker_tool = docker_tool
        self._settings = get_runtime_settings()

    def execute(self, context: SkillContext) -> Iterator[dict]:
        messages = self._build_messages(context)

        yield {
            "type": "step_started",
            "step": "docker_analysis",
            "detail": "Analyzing Docker request.",
        }

        last_tool_result = None

        for iteration in range(self._settings.agent_max_turns):
            response = self._model_client.chat(
                messages=messages,
                tools=[self._docker_tool.schema],
            )

            assistant_message = response.get("message", {})
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                reply = assistant_message.get("content", "")

                yield {
                    "type": "step_completed",
                    "step": "docker_analysis",
                    "detail": "Final Docker response generated.",
                }

                for token in self._chunk_text(reply):
                    yield {"type": "token", "content": token}

                yield {"type": "done"}
                return

            messages.append(assistant_message)

            for tool_call in tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")
                arguments = function_call.get("arguments", {}) or {}

                if isinstance(arguments, str):
                    arguments = json.loads(arguments)

                yield {
                    "type": "tool_called",
                    "tool_name": tool_name,
                    "action": arguments.get("action"),
                    "iteration": iteration + 1,
                }

                tool_event, tool_content = self._docker_tool.execute(
                    server_id=context.server_id,
                    arguments=arguments,
                )

                last_tool_result = tool_content
                messages.append({"role": "tool", "content": tool_content})

                yield {
                    "type": "tool_event",
                    "tool_name": tool_event.tool_name,
                    "command": tool_event.command,
                    "exit_status": tool_event.exit_status,
                    "stdout": tool_event.stdout,
                    "stderr": tool_event.stderr,
                }

        fallback = f"Last Docker output:\n{last_tool_result}"

        yield {
            "type": "step_completed",
            "step": "docker_analysis",
            "detail": "Fallback used.",
        }

        for token in self._chunk_text(fallback):
            yield {"type": "token", "content": token}

        yield {"type": "done"}

    @staticmethod
    def _chunk_text(text: str):
        for word in text.split(" "):
            yield word + " "

    @staticmethod
    def _build_messages(context: SkillContext):
        system_message = {
            "role": "system",
            "content": (
                "You are a Docker specialist for a Linux server manager. \n"
                "Use docker tools to manage containers and deployments.\n "
                "First check whether docker is installed or not on  the server , if not then install docker with strictly users permission , then only go forward, use ssh_skills and ssh_tools for this \n"
                "Capabilities:\n"
                "- Build images\n"
                "- Run containers\n"
                "- Stop/remove containers\n"
                "- View logs and status\n\n"
                "Rules:\n"
                "Never remove containers without explicit confirmation."
                "- Always confirm before stopping/removing containers\n"
                "- Prefer safe read commands first\n"
                "- If user says 'deploy app' → build + run container\n"
                "- Use port mappings when needed\n"
                "- Do not install Docker unless explicitly asked\n"
                "- Keep responses concise and action-oriented"
            ),
        }

        return [
            system_message,
            *context.history[-10:],
            {"role": "user", "content": context.user_message},
        ]