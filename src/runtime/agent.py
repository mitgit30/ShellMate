from collections.abc import Iterator

from src.memory.context_extractor import ContextExtractor
from src.runtime.models import AgentTurnResult, ToolEvent
from src.skills.base import SkillContext
from src.skills.registry import SkillRegistry
from src.skills.router import SkillRouter


class ServerOpsAgent:
    def __init__(
        self,
        skill_router: SkillRouter,
        skill_registry: SkillRegistry,
        session_store,
        context_extractor: ContextExtractor,
    ) -> None:
        self._skill_router = skill_router
        self._skill_registry = skill_registry
        self._session_store = session_store
        self._context_extractor = context_extractor

    def handle_turn(self, session_id: str, server_id: str, user_message: str) -> AgentTurnResult:
        reply_parts: list[str] = []
        tool_events: list[ToolEvent] = []

        for event in self.stream_turn(
            session_id=session_id,
            server_id=server_id,
            user_message=user_message,
        ):
            if event["type"] == "token":
                reply_parts.append(event["content"])
            elif event["type"] == "tool_event":
                tool_events.append(
                    ToolEvent(
                        tool_name=event["tool_name"],
                        command=event["command"],
                        exit_status=event["exit_status"],
                        stdout=event.get("stdout", ""),
                        stderr=event.get("stderr", ""),
                    )
                )

        return AgentTurnResult(reply="".join(reply_parts).strip(), tool_events=tool_events)

    def stream_turn(self, session_id: str, server_id: str, user_message: str) -> Iterator[dict]:
        session = self._session_store.get_or_create(session_id=session_id, server_id=server_id)
        history = session.messages[-10:] # Limit history to the last 10 messages for routing and context.

        try:
            route = self._skill_router.route(user_message=user_message, history=history)
        except Exception as exc:
            fallback_reply = self._runtime_failure_message(
                "I ran into a problem while deciding how to handle that request.",
                exc,
            )
            yield {"type": "error", "detail": fallback_reply}
            yield {"type": "done"}
            self._persist_session(session=session, user_message=user_message, reply=fallback_reply)
            return

        yield {"type": "intent_detected", "detail": route.reason}
        yield {
            "type": "skill_selected",
            "skill_id": route.skill_id,
            "reason": route.reason,
        }

        try:
            skill = self._skill_registry.get(route.skill_id)
        except Exception as exc:
            fallback_reply = self._runtime_failure_message(
                "I selected a workflow for the request, but I couldn't load it correctly.",
                exc,
            )
            yield {"type": "error", "detail": fallback_reply}
            yield {"type": "done"}
            self._persist_session(session=session, user_message=user_message, reply=fallback_reply)
            return

        context = SkillContext(
            session_id=session_id,
            server_id=server_id,
            user_message=user_message,
            history=history,
            session_state=session.metadata,
        )

        reply_parts: list[str] = []
        tool_outputs: list[str] = []
        try:
            for event in skill.execute(context):
                if event["type"] == "token":
                    reply_parts.append(event["content"])
                elif event["type"] == "tool_event":
                    stdout = event.get("stdout", "")
                    stderr = event.get("stderr", "")
                    if stdout:
                        tool_outputs.append(stdout)
                    if stderr:
                        tool_outputs.append(stderr)
                yield event
        except Exception as exc:
            fallback_reply = self._runtime_failure_message(
                "I started working on that request, but the execution flow failed unexpectedly.",
                exc,
            )
            yield {"type": "error", "detail": fallback_reply}
            yield {"type": "done"}
            self._persist_session(session=session, user_message=user_message, reply=fallback_reply)
            return

        reply = "".join(reply_parts).strip()
        try:
            self._context_extractor.extract(
                server_id=server_id,
                user_message=user_message,
                assistant_message=reply,
                tool_outputs=tool_outputs,
            )
        except Exception:
            # Memory extraction should never break the visible agent turn.
            pass

        self._persist_session(
            session=session,
            user_message=user_message,
            reply=reply,
        )

    @staticmethod
    def _persist_session(session, user_message: str, reply: str) -> None:
        session.messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": reply},
            ]
        )

    @staticmethod
    def _runtime_failure_message(prefix: str, exc: Exception) -> str:
        detail = str(exc).strip()
        if detail:
            return f"{prefix}\n\nDetails: {detail}"
        return prefix
