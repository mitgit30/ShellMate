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


class ChatHistoryMessage(BaseModel):
    role: str
    content: str
    created_at: str


class ChatSessionCreate(BaseModel):
    server_id: str = Field(min_length=1, max_length=100)
    title: str = Field(default="New chat", min_length=1, max_length=120)


class ChatSessionSummary(BaseModel):
    session_id: str
    server_id: str
    title: str
    created_at: str
    updated_at: str
