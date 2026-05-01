import json

from src.runtime.config import get_runtime_settings
from src.runtime.models import AgentTurnResult, ToolEvent
from src.runtime.ollama_client import OllamaModelClient
from src.storage.session_store import InMemorySessionStore
from src.tools.ssh_tool import SSHCommandTool


class ServerOpsAgent:
    def __init__(
        self,
        model_client: OllamaModelClient,
        session_store: InMemorySessionStore,
        ssh_tool: SSHCommandTool,
    ) -> None:
        self._model_client = model_client
        self._session_store = session_store
        self._ssh_tool = ssh_tool
        self._settings = get_runtime_settings()

    def handle_turn(self, session_id: str, server_id: str, user_message: str) -> AgentTurnResult:
        session = self._session_store.get_or_create(session_id=session_id, server_id=server_id)
        tool_events: list[ToolEvent] = []

        system_message = {
            "role": "system",
            "content": (
                "You are a Linux server operations agent. "
                "Help users inspect and manage the connected Linux server. "
                "When real server information is required, call the SSH tool. "
                "Prefer safe read-focused commands unless the user explicitly requests a change. "
                "After tool use, explain the result clearly."
            ),
        }
        history = session.messages[-10:]
        messages = [system_message, *history, {"role": "user", "content": user_message}]

        for _ in range(self._settings.agent_max_turns):
            response = self._model_client.chat(messages=messages, tools=[self._ssh_tool.schema])
            assistant_message = response.get("message", {})
            messages.append(assistant_message)

            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                reply = assistant_message.get("content", "") or "No response generated."
                session.messages.extend(
                    [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": reply},
                    ]
                )
                return AgentTurnResult(reply=reply, tool_events=tool_events)

            for tool_call in tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")
                arguments = function_call.get("arguments", {}) or {}
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)

                if tool_name != self._ssh_tool.name:
                    raise ValueError(f"Unsupported tool call '{tool_name}'.")

                tool_event, tool_content = self._ssh_tool.execute(
                    server_id=server_id,
                    arguments=arguments,
                )
                tool_events.append(tool_event)
                messages.append({"role": "tool", "content": tool_content})

        raise RuntimeError("Agent exceeded the maximum number of tool iterations.")
