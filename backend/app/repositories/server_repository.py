from collections.abc import Iterable

from backend.app.schemas.server import ServerRecord


class InMemoryServerRepository:
    """Prototype repository for registered Linux hosts."""

    def __init__(self) -> None:
        self._servers: dict[str, ServerRecord] = {}

    def list(self) -> Iterable[ServerRecord]:
        return self._servers.values()

    def get(self, server_id: str) -> ServerRecord | None:
        return self._servers.get(server_id)

    def add(self, server: ServerRecord) -> None:
        self._servers[server.id] = server
