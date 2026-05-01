from pydantic import BaseModel, Field


class ToolEvent(BaseModel):
    tool_name: str
    command: str
    exit_status: int
    stdout: str = ""
    stderr: str = ""


class AgentTurnResult(BaseModel):
    reply: str
    tool_events: list[ToolEvent] = Field(default_factory=list)
