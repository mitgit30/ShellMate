from pydantic import BaseModel, Field, model_validator


class ServerCreate(BaseModel):
    id: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9-_]+$")
    name: str = Field(min_length=2, max_length=100)
    host: str = Field(min_length=7, max_length=15, description="Public IPv4 address")
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=100)
    private_key_path: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_authentication(self) -> "ServerCreate":
        if not self.private_key_path.lower().endswith(".pem"):
            raise ValueError("private_key_path must point to a .pem file.")
        octets = self.host.split(".")
        if len(octets) != 4 or any(not octet.isdigit() for octet in octets):
            raise ValueError("host must be a valid IPv4 address.")
        if any(int(octet) < 0 or int(octet) > 255 for octet in octets):
            raise ValueError("host must be a valid IPv4 address.")

        return self


class ServerRecord(ServerCreate):
    pass


class ServerResponse(BaseModel):
    id: str
    name: str
    host: str
    port: int
    username: str
    private_key_path: str

    @classmethod
    def from_record(cls, record: ServerRecord) -> "ServerResponse":
        return cls(
            id=record.id,
            name=record.name,
            host=record.host,
            port=record.port,
            username=record.username,
            private_key_path=record.private_key_path,
        )


class ServerConnectionTestResponse(BaseModel):
    server_id: str
    is_reachable: bool
