import json
from collections.abc import Iterator

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
        messages = self._build_messages(session.messages[-10:], user_message)
        resolved_messages, tool_events, direct_reply = self._resolve_tool_loop(
            messages=messages,
            server_id=server_id,
        )

        if direct_reply is not None:
            reply = direct_reply
        else:
            reply = self._collect_streamed_reply(resolved_messages)

        self._persist_session(session, user_message=user_message, reply=reply)
        return AgentTurnResult(reply=reply, tool_events=tool_events)

    def stream_turn(self, session_id: str, server_id: str, user_message: str) -> Iterator[dict]:
        session = self._session_store.get_or_create(session_id=session_id, server_id=server_id)
        messages = self._build_messages(session.messages[-10:], user_message)
        resolved_messages, tool_events, direct_reply = self._resolve_tool_loop(
            messages=messages,
            server_id=server_id,
        )

        reply_parts: list[str] = []
        for event in tool_events:
            yield {
                "type": "tool_event",
                "tool_name": event.tool_name,
                "command": event.command,
                "exit_status": event.exit_status,
            }

        if direct_reply is not None:
            for token in self._chunk_text(direct_reply):
                reply_parts.append(token)
                yield {"type": "token", "content": token}
        else:
            for token in self._stream_reply_tokens(resolved_messages):
                reply_parts.append(token)
                yield {"type": "token", "content": token}

        reply = "".join(reply_parts).strip()
        self._persist_session(session, user_message=user_message, reply=reply)
        yield {"type": "done"}

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix

    def _stream_reply_tokens(self, messages: list[dict]) -> Iterator[str]:
        stream = self._model_client.chat_stream(messages=messages)
        for chunk in stream:
            message = chunk.message
            if message and message.content:
                yield message.content

    def _collect_streamed_reply(self, messages: list[dict]) -> str:
        return "".join(self._stream_reply_tokens(messages)).strip()

    def _build_messages(self, history: list[dict], user_message: str) -> list[dict]:
        return [self._system_message(), *history, {"role": "user", "content": user_message}]

    @staticmethod
    def _persist_session(session, user_message: str, reply: str) -> None:
        session.messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ]
        )

    def _resolve_tool_loop(
        self,
        messages: list[dict],
        server_id: str,
    ) -> tuple[list[dict], list[ToolEvent], str | None]:
        tool_events: list[ToolEvent] = []
        last_tool_result: str | None = None

        for _ in range(self._settings.agent_max_turns):
            response = self._model_client.chat(messages=messages, tools=[self._ssh_tool.schema])
            assistant_message = response.get("message", {})
            tool_calls = assistant_message.get("tool_calls") or []
            if not tool_calls:
                reply = assistant_message.get("content", "") or "No response generated."
                return messages, tool_events, reply

            messages.append(assistant_message)
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
                last_tool_result = tool_content
                messages.append({"role": "tool", "content": tool_content})

        if last_tool_result is not None:
            fallback_reply = (
                "I executed the latest server command but the model did not finish"
                " the response cleanly. Here is the latest result:\n\n"
                f"```text\n{last_tool_result}\n```"
            )
            return messages, tool_events, fallback_reply

        raise RuntimeError("Agent exceeded the maximum number of tool iterations.")

    @staticmethod
    def _system_message() -> dict:
        return {
            "role": "system",
            "content": (
                "You are a Linux server operations agent. "
                "Help users inspect and manage the connected Linux server. "
                "When real server information is required, call the SSH tool. "
                "Prefer safe read-focused commands unless the user explicitly requests a change. "
                "After a successful tool result, answer the user directly unless another tool call is absolutely necessary."
            ),
        }
