from collections.abc import Iterator

from src.runtime.models import AgentTurnResult, ToolEvent
from src.runtime.server_context import ContextExtractor, ServerContext
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
        server_context = ServerContext.from_json(session.server_context_json)

        route = self._skill_router.route(user_message=user_message, history=history)
        yield {"type": "intent_detected", "detail": route.reason}
        yield {
            "type": "skill_selected",
            "skill_id": route.skill_id,
            "reason": route.reason,
        }

        skill = self._skill_registry.get(route.skill_id)
        context = SkillContext(
            session_id=session_id,
            server_id=server_id,
            user_message=user_message,
            history=history,
            server_context=server_context,
        )

        reply_parts: list[str] = []
        tool_outputs: list[str] = []
        for event in skill.execute(context):
            if event["type"] == "token":
                reply_parts.append(event["content"])
            elif event["type"] == "tool_event":
                tool_outputs.append(event.get("stdout", "") or event.get("stderr", ""))
            yield event

        reply = "".join(reply_parts).strip()
        updated_context = self._context_extractor.extract(
            assistant_message=reply,
            server_context=context.server_context,
            user_message=user_message,
            tool_outputs=tool_outputs,
        )
        session.server_context_json = updated_context.to_json()
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
