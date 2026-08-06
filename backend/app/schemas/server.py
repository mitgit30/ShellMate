from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class ServerCreate(BaseModel):
    id: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9-_]+$")
    name: str = Field(min_length=2, max_length=100)
    host: str = Field(min_length=7, max_length=15, description="Public IPv4 address")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=100)
    key_id: str | None = Field(default=None, min_length=1, max_length=100)
    # Accepted temporarily for existing local registrations. New clients must
    # send key_id; this field is never returned by the public API.
    private_key_path: str | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_authentication(self) -> "ServerCreate":
        if not self.key_id and not self.private_key_path:
            raise ValueError("key_id is required.")
        if self.key_id and (
            Path(self.key_id).name != self.key_id
            or "/" in self.key_id
            or "\\" in self.key_id
        ):
            raise ValueError("key_id must be a filename identifier, not a path.")
        octets = self.host.split(".")
        if len(octets) != 4 or any(not octet.isdigit() for octet in octets):
            raise ValueError("host must be a valid IPv4 address.")
        if any(int(octet) < 0 or int(octet) > 255 for octet in octets):
            raise ValueError("host must be a valid IPv4 address.")

        return self


class ServerRecord(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    private_key_path: str
    user_id: str | None = None


class ServerResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    key_id: str

    @classmethod
    def from_record(cls, record: ServerRecord) -> "ServerResponse":
        return cls(
            id=record.id,
            name=record.name,
            host=record.host,
            port=record.port,
            username=record.username,
            key_id=Path(record.private_key_path).name,
        )


class ServerConnectionTestResponse(BaseModel):
    server_id: str
    is_reachable: bool
