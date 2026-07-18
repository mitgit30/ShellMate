import logging
from collections.abc import Iterator

from src.memory.context_extractor import ContextExtractor
from src.runtime.models import AgentEvent, AgentTurnResult, ToolEvent
from src.skills.base import SkillContext
from src.skills.registry import SkillRegistry
from src.skills.router import SkillRouter

logger = logging.getLogger(__name__)


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
            if event.type == "token":
                reply_parts.append(event.content or "")
            elif event.type == "tool_event":
                tool_events.append(
                    ToolEvent(
                        tool_name=event.tool_name or "",
                        command=event.command or "",
                        exit_status=event.exit_status or 0,
                        stdout=event.stdout,
                        stderr=event.stderr,
                    )
                )

        return AgentTurnResult(reply="".join(reply_parts).strip(), tool_events=tool_events)

    def stream_turn(
        self,
        session_id: str,
        server_id: str,
        user_message: str,
    ) -> Iterator[AgentEvent]:
        session = self._session_store.get_or_create(session_id=session_id, server_id=server_id)
        history = session.messages[-10:]

        try:
            route = self._skill_router.route(user_message=user_message, history=history)
        except Exception as exc:
            logger.exception("Skill routing failed", extra={"session_id": session_id, "server_id": server_id})
            fallback_reply = self._runtime_failure_message(
                "I ran into a problem while deciding how to handle that request.",
                exc,
            )
            yield AgentEvent(type="error", detail=fallback_reply)
            yield AgentEvent(type="done")
            self._persist_session(session=session, user_message=user_message, reply=fallback_reply)
            return

        yield AgentEvent(type="intent_detected", detail=route.reason)
        yield AgentEvent(
            type="skill_selected",
            skill_id=route.skill_id,
            reason=route.reason,
        )

        try:
            skill = self._skill_registry.get(route.skill_id)
        except Exception as exc:
            logger.exception("Skill loading failed", extra={"session_id": session_id, "server_id": server_id, "skill_id": route.skill_id})
            fallback_reply = self._runtime_failure_message(
                "I selected a workflow for the request, but I couldn't load it correctly.",
                exc,
            )
            yield AgentEvent(type="error", detail=fallback_reply)
            yield AgentEvent(type="done")
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
            for raw_event in skill.execute(context):
                event = AgentEvent.model_validate(raw_event)
                if event.type == "token":
                    reply_parts.append(event.content or "")
                elif event.type == "tool_event":
                    if event.stdout:
                        tool_outputs.append(event.stdout)
                    if event.stderr:
                        tool_outputs.append(event.stderr)
                yield event
        except Exception as exc:
            logger.exception("Skill execution failed", extra={"session_id": session_id, "server_id": server_id, "skill_id": route.skill_id})
            fallback_reply = self._runtime_failure_message(
                "I started working on that request, but the execution flow failed unexpectedly.",
                exc,
            )
            yield AgentEvent(type="error", detail=fallback_reply)
            yield AgentEvent(type="done")
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
            logger.exception("Memory extraction failed", extra={"session_id": session_id, "server_id": server_id})

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
        """Return a safe user-facing message; the exception is logged by the caller."""
        return prefix
