from pydantic import BaseModel, Field


class CommandExecutionRequest(BaseModel):
    server_id: str
    command: str = Field(min_length=1, max_length=4000)


class CommandExecutionResponse(BaseModel):
    server_id: str
    command: str
    stdout: str
    stderr: str
    exit_status: int
