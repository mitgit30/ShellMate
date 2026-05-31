import json
from collections.abc import Iterator

from src.runtime.config import get_runtime_settings
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext
from src.tools.ssh_tool import SSHCommandTool


class SSHSkill(BaseSkill):
    id = "ssh"
    name = "SSH Operations"
    description = (
        "Handles Linux server tasks over SSH, including diagnostics, status checks, "
        "services, logs, files, and command-driven operations."
    )

    def __init__(self, model_client: OllamaModelClient, ssh_tool: SSHCommandTool) -> None:
        self._model_client = model_client
        self._ssh_tool = ssh_tool
        self._settings = get_runtime_settings()

    def execute(self, context: SkillContext) -> Iterator[dict]:
        messages = self._build_messages(context)
        yield {
            "type": "step_started",
            "step": "ssh_skill_analysis",
            "detail": "Analyzing the SSH request and deciding which server commands are needed.",
        }

        last_tool_result: str | None = None
        for iteration in range(self._settings.agent_max_turns):
            response = self._model_client.chat(
                messages=messages,
                tools=[self._ssh_tool.schema],
            )
            assistant_message = response.get("message", {})
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                reply = assistant_message.get("content", "") or "No response generated."
                yield {
                    "type": "step_completed",
                    "step": "ssh_skill_analysis",
                    "detail": "Generated a final SSH response.",
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

                if tool_name != self._ssh_tool.name:
                    raise ValueError(f"Unsupported tool call '{tool_name}'.")

                command = str(arguments.get("command", "")).strip()
                yield {
                    "type": "tool_called",
                    "tool_name": tool_name,
                    "command": command,
                    "iteration": iteration + 1,
                }

                tool_event, tool_content = self._ssh_tool.execute(
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

        fallback_reply = (
            "I executed the SSH command, but the model did not finish the response cleanly. "
            "Here is the latest result:\n\n"
            f"{last_tool_result or 'No tool output was produced.'}"
        )
        yield {
            "type": "step_completed",
            "step": "ssh_skill_analysis",
            "detail": "Returned a fallback response after repeated tool iterations.",
        }
        for token in self._chunk_text(fallback_reply):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix

    @staticmethod
    def _build_messages(context: SkillContext) -> list[dict]:
        system_message = {
            "role": "system",
            "content": (
                "You are the SSH skill for a Linux server manager. "
                "This request has already been routed to you. "
                "Use the SSH tool whenever live server information or action is required. "
                "Prefer safe, read-focused commands unless the user clearly requests a change. "
                "After enough tool results are available, answer directly and stop calling tools. "
                "Only execute install/upgrade/remove commands after the user explicitly approves them."
                "Dont install any packages  without explicit user confirmation. "
                "You can explain the raw data (disk usage,ram usage etc whenever you get it from the server) , just dont dump all raw data to response.. the response should be user friendly"
                "Do not mention routing, skills, tool calls, or internal analysis unless the user explicitly asks for those details. "
                "Respond like a concise systems assistant focused on the user's outcome."
                "Never issue a destructive/ change‑making command (e.g., package installs, service restarts) without first asking the user for explicit confirmation.\n\n"
                "Structured server context:\n"
                f"{context.server_context.prompt_summary()}"
            ),
        }
        return [
            system_message,
            *context.history[-10:],
            {"role": "user", "content": context.user_message},
        ]
