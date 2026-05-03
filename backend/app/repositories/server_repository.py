import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from backend.app.schemas.server import ServerRecord


class ServerRepository(Protocol):
    def list(self) -> Iterable[ServerRecord]:
        ...

    def get(self, server_id: str) -> ServerRecord | None:
        ...

    def add(self, server: ServerRecord) -> None:
        ...


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


class SQLiteServerRepository:
    """SQLite-backed repository for registered Linux hosts."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def list(self) -> Iterable[ServerRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, host, port, username, private_key_path
                FROM servers
                ORDER BY name, id
                """
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, server_id: str) -> ServerRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, host, port, username, private_key_path
                FROM servers
                WHERE id = ?
                """,
                (server_id,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_record(row)

    def add(self, server: ServerRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO servers (id, name, host, port, username, private_key_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    server.id,
                    server.name,
                    server.host,
                    server.port,
                    server.username,
                    server.private_key_path,
                ),
            )
            connection.commit()

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS servers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    private_key_path TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ServerRecord:
        return ServerRecord(
            id=row["id"],
            name=row["name"],
            host=row["host"],
            port=row["port"],
            username=row["username"],
            private_key_path=row["private_key_path"],
        )
