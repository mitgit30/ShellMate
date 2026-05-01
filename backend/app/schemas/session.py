from pydantic import BaseModel


class SSHSessionConnectRequest(BaseModel):
    server_id: str


class SSHSessionResponse(BaseModel):
    server_id: str
    connected: bool
    message: str
