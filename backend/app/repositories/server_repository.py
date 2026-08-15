from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from backend.app.db.database import Database
from backend.app.schemas.server import ServerRecord


class ServerRepository(Protocol):
    def list(self, user_id: str | None = None) -> Iterable[ServerRecord]:
        ...

    def get(self, server_id: str, user_id: str) -> ServerRecord | None:
        ...

    def get_by_id(self, server_id: str) -> ServerRecord | None:
        ...

    def add(self, server: ServerRecord) -> None:
        ...

    def update_key(self, server_id: str, private_key_path: str) -> None:
        ...

    def assign_unowned_servers(self, user_id: str) -> None:
        ...


class InMemoryServerRepository:
    """Prototype repository for registered Linux hosts."""

    def __init__(self) -> None:
        self._servers: dict[str, ServerRecord] = {}

    def list(self, user_id: str | None = None) -> Iterable[ServerRecord]:
        return [server for server in self._servers.values() if user_id is None or server.user_id == user_id]

    def get(self, server_id: str, user_id: str) -> ServerRecord | None:
        server = self._servers.get(server_id)
        return server if server and server.user_id == user_id else None

    def get_by_id(self, server_id: str) -> ServerRecord | None:
        return self._servers.get(server_id)

    def add(self, server: ServerRecord) -> None:
        self._servers[server.id] = server

    def update_key(self, server_id: str, private_key_path: str) -> None:
        server = self._servers[server_id]
        self._servers[server_id] = server.model_copy(update={"private_key_path": private_key_path})

    def assign_unowned_servers(self, user_id: str) -> None:
        return None


class SQLiteServerRepository:
    """SQLite-backed repository for registered Linux hosts."""

    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/servers.db"))
        self._database.initialize_schema()

    def list(self, user_id: str | None = None) -> Iterable[ServerRecord]:
        with self._database.connect() as connection:
            if user_id is None:
                rows = connection.execute(
                    """SELECT id, name, host, port, username, private_key_path, user_id
                    FROM servers ORDER BY name, id"""
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT id, name, host, port, username, private_key_path, user_id
                    FROM servers WHERE user_id = ? ORDER BY name, id""",
                    (user_id,),
                ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, server_id: str, user_id: str) -> ServerRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, host, port, username, private_key_path, user_id
                FROM servers WHERE id = ? AND user_id = ?
                """,
                (server_id, user_id),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_record(row)

    def get_by_id(self, server_id: str) -> ServerRecord | None:
        with self._database.connect() as connection:
            row = connection.execute(
                "SELECT id, name, host, port, username, private_key_path, user_id FROM servers WHERE id = ?",
                (server_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def add(self, server: ServerRecord) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """
                INSERT INTO servers (id, name, host, port, username, private_key_path, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    server.id,
                    server.name,
                    server.host,
                    server.port,
                    server.username,
                    server.private_key_path,
                    server.user_id,
                ),
            )
            connection.commit()

    def update_key(self, server_id: str, private_key_path: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                "UPDATE servers SET private_key_path = ? WHERE id = ?",
                (private_key_path, server_id),
            )
            connection.commit()

    def assign_unowned_servers(self, user_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute("UPDATE servers SET user_id = ? WHERE user_id IS NULL", (user_id,))
            connection.commit()

    @staticmethod
    def _row_to_record(row) -> ServerRecord:
        return ServerRecord(
            id=row["id"],
            name=row["name"],
            host=row["host"],
            port=row["port"],
            username=row["username"],
            private_key_path=row["private_key_path"],
            user_id=row["user_id"],
        )


# Preserve the existing dependency import while making the implementation
# database-engine agnostic.
DatabaseServerRepository = SQLiteServerRepository
