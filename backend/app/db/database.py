"""Small database adapter supporting PostgreSQL and local SQLite.

The application services use one connection contract, while the configured
``DATABASE_URL`` decides which database engine is used. SQLite remains a
useful local fallback; PostgreSQL is the production path.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine


class DatabaseRow(dict):
    """Mapping row compatible with the existing mapping and tuple access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class DatabaseResult:
    def __init__(self, rows: list[DatabaseRow], rowcount: int = -1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def fetchone(self) -> DatabaseRow | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[DatabaseRow]:
        return list(self._rows)


class DatabaseConnection:
    def __init__(self, connection: Connection, postgres: bool) -> None:
        self._connection = connection
        self._postgres = postgres
        self._transaction = connection.begin()

    def execute(self, sql: str, parameters: Iterable[Any] = ()) -> DatabaseResult:
        statement = sql.replace("?", "%s") if self._postgres else sql
        result = self._connection.exec_driver_sql(statement, tuple(parameters))
        rows: list[DatabaseRow] = []
        if result.returns_rows:
            rows = [DatabaseRow(dict(row._mapping)) for row in result.fetchall()]
        return DatabaseResult(rows, result.rowcount)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self._transaction.commit()
        self._transaction = self._connection.begin()

    def rollback(self) -> None:
        if self._transaction.is_active:
            self._transaction.rollback()

    def __enter__(self) -> "DatabaseConnection":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self._connection.close()


class Database:
    def __init__(self, database_url: str | None, sqlite_path: Path) -> None:
        self._schema_initialized = False
        self._initializing_schema = False
        self.is_postgres = bool(database_url and database_url.startswith(("postgresql", "postgres")))
        if database_url:
            connect_args = {} if "connect_timeout=" in database_url else {"connect_timeout": 5}
            self.engine: Engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
                pool_timeout=10,
                connect_args=connect_args,
            )
        else:
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(
                f"sqlite:///{sqlite_path.as_posix()}",
                connect_args={"check_same_thread": False, "timeout": 30},
                pool_pre_ping=True,
            )

    def connect(self) -> DatabaseConnection:
        # Retry schema initialization lazily after a transient startup outage.
        # This lets the API recover when PostgreSQL is started after the backend.
        if not self._schema_initialized and not self._initializing_schema:
            self.initialize_schema()
        return DatabaseConnection(self.engine.connect(), self.is_postgres)

    def initialize_schema(self) -> None:
        if self._schema_initialized:
            return
        self._initializing_schema = True
        identity = "BIGSERIAL" if self.is_postgres else "INTEGER"
        auto_suffix = "" if self.is_postgres else " AUTOINCREMENT"
        try:
            with DatabaseConnection(self.engine.connect(), self.is_postgres) as connection:
                connection.executescript(
                    f"""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS servers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    private_key_path TEXT NOT NULL,
                    user_id TEXT REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_servers_user ON servers(user_id);
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    server_id TEXT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id {identity} PRIMARY KEY{auto_suffix},
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
                    server_id TEXT NOT NULL REFERENCES servers(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                    ON chat_messages(user_id, session_id, server_id, message_id);
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_skill TEXT,
                    current_step TEXT,
                    deployment_status TEXT NOT NULL DEFAULT 'not_applicable',
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    error_message TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_user
                    ON agent_tasks(user_id, server_id, started_at);
                CREATE TABLE IF NOT EXISTS agent_events (
                    event_id {identity} PRIMARY KEY{auto_suffix},
                    task_id TEXT NOT NULL REFERENCES agent_tasks(task_id) ON DELETE CASCADE,
                    event_type TEXT NOT NULL,
                    detail TEXT,
                    skill_id TEXT,
                    step TEXT,
                    tool_name TEXT,
                    command TEXT,
                    iteration INTEGER,
                    exit_status INTEGER,
                    created_at TIMESTAMP NOT NULL
                );
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_documents (
                    server_id TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (server_id, document_type)
                );
                CREATE TABLE IF NOT EXISTS memory_facts (
                    server_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    observed_at TIMESTAMP NOT NULL,
                    expires_at TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (server_id, category, fact_key)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_facts_server_category
                    ON memory_facts(server_id, category);
                CREATE INDEX IF NOT EXISTS idx_memory_facts_expiry
                    ON memory_facts(server_id, expires_at);
                CREATE TABLE IF NOT EXISTS memory_observations (
                    id {identity} PRIMARY KEY{auto_suffix},
                    server_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    observed_at TIMESTAMP NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_observations_server_time
                    ON memory_observations(server_id, observed_at);
                """
                )
                connection.execute(
                    "INSERT INTO schema_metadata(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    ("schema_version", "2"),
                )
            self._schema_initialized = True
        finally:
            self._initializing_schema = False
