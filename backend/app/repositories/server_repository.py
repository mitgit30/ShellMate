import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from backend.app.schemas.server import ServerRecord


class ServerRepository(Protocol):
    def list(self, user_id: str) -> Iterable[ServerRecord]:
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

    def list(self, user_id: str) -> Iterable[ServerRecord]:
        return [server for server in self._servers.values() if server.user_id == user_id]

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

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def list(self, user_id: str) -> Iterable[ServerRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, host, port, username, private_key_path, user_id
                FROM servers
                WHERE user_id = ?
                ORDER BY name, id
                """, (user_id,)
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get(self, server_id: str, user_id: str) -> ServerRecord | None:
        with self._connect() as connection:
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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, host, port, username, private_key_path, user_id FROM servers WHERE id = ?",
                (server_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def add(self, server: ServerRecord) -> None:
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.execute(
                "UPDATE servers SET private_key_path = ? WHERE id = ?",
                (private_key_path, server_id),
            )
            connection.commit()

    def assign_unowned_servers(self, user_id: str) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE servers SET user_id = ? WHERE user_id IS NULL", (user_id,))
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
                    private_key_path TEXT NOT NULL,
                    user_id TEXT
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(servers)")}
            if "user_id" not in columns:
                connection.execute("ALTER TABLE servers ADD COLUMN user_id TEXT")
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
            user_id=row["user_id"],
        )
