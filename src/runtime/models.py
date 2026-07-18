from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field


EventType = Literal[
    "token",
    "done",
    "error",
    "intent_detected",
    "skill_selected",
    "step_started",
    "step_completed",
    "tool_called",
    "tool_event",
]


class AgentEvent(BaseModel):
    """Typed runtime event emitted by skills and exposed by the chat transports."""

    model_config = ConfigDict(extra="allow")

    type: EventType
    content: str | None = None
    detail: str | None = None
    skill_id: str | None = None
    reason: str | None = None
    step: str | None = None
    tool_name: str | None = None
    command: str | None = None
    iteration: int | None = None
    exit_status: int | None = None
    stdout: str = ""
    stderr: str = ""
    status_code: int | None = None

    def as_payload(self) -> dict[str, Any]:
        """Return the transport-safe JSON payload for this event."""
        return self.model_dump(
            mode="json",
            exclude_none=True,
            exclude_unset=True,
        )


class ToolEvent(BaseModel):
    tool_name: str
    command: str
    exit_status: int
    stdout: str = ""
    stderr: str = ""


class AgentTurnResult(BaseModel):
    reply: str
    tool_events: list[ToolEvent] = Field(default_factory=list)


class SkillRouteDecision(BaseModel):
    skill_id: str
    reason: str