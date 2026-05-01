from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    server_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=4000)


class ChatToolEvent(BaseModel):
    tool_name: str
    command: str
    exit_status: int


class ChatResponse(BaseModel):
    session_id: str
    server_id: str
    reply: str
    tool_events: list[ChatToolEvent] = Field(default_factory=list)
