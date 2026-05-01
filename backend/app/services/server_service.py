from backend.app.core.exceptions import ServerAlreadyExistsError, ServerNotFoundError
from backend.app.repositories.server_repository import InMemoryServerRepository
from backend.app.schemas.server import ServerCreate, ServerRecord, ServerResponse


class ServerService:
    def __init__(self, server_repository: InMemoryServerRepository) -> None:
        self._server_repository = server_repository

    def list_servers(self) -> list[ServerResponse]:
        return [
            ServerResponse.from_record(record)
            for record in self._server_repository.list()
        ]

    def create_server(self, payload: ServerCreate) -> ServerResponse:
        existing_server = self._server_repository.get(payload.id)
        if existing_server is not None:
            raise ServerAlreadyExistsError(
                f"Server with id '{payload.id}' is already registered."
            )

        record = ServerRecord(**payload.model_dump())
        self._server_repository.add(record)
        return ServerResponse.from_record(record)

    def get_server(self, server_id: str) -> ServerResponse:
        record = self._get_server_record(server_id)
        return ServerResponse.from_record(record)

    def get_server_record(self, server_id: str) -> ServerRecord:
        return self._get_server_record(server_id)

    def _get_server_record(self, server_id: str) -> ServerRecord:
        record = self._server_repository.get(server_id)
        if record is None:
            raise ServerNotFoundError(f"Server with id '{server_id}' was not found.")
        return record
