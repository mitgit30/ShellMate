"""SQLite persistence for ShellMate server memory."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


class SQLiteMemoryStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_documents (
                    server_id TEXT NOT NULL,
                    document_type TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (server_id, document_type)
                );

                CREATE TABLE IF NOT EXISTS memory_facts (
                    server_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    observed_at TEXT NOT NULL,
                    expires_at TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (server_id, category, fact_key)
                );

                CREATE TABLE IF NOT EXISTS memory_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    observed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memory_facts_server_category
                    ON memory_facts(server_id, category);
                CREATE INDEX IF NOT EXISTS idx_memory_facts_expiry
                    ON memory_facts(server_id, expires_at);
                CREATE INDEX IF NOT EXISTS idx_memory_observations_server_time
                    ON memory_observations(server_id, observed_at);
                """
            )
            connection.execute(
                "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_document(self, server_id: str, document_type: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT content FROM memory_documents WHERE server_id = ? AND document_type = ?",
                (server_id, document_type),
            ).fetchone()
        return str(row["content"]) if row else ""

    def save_document(self, server_id: str, document_type: str, content: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_documents(server_id, document_type, content, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(server_id, document_type) DO UPDATE SET
                    content = excluded.content,
                    updated_at = excluded.updated_at
                """,
                (server_id, document_type, content, self._now()),
            )

    def upsert_fact(
        self,
        server_id: str,
        category: str,
        fact_key: str,
        value: Any,
        source: str = "unknown",
        confidence: float = 1.0,
        expires_at: str | None = None,
    ) -> None:
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memory_facts(
                    server_id, category, fact_key, value_json, source,
                    confidence, observed_at, expires_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(server_id, category, fact_key) DO UPDATE SET
                    value_json = excluded.value_json,
                    source = excluded.source,
                    confidence = excluded.confidence,
                    observed_at = excluded.observed_at,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    server_id,
                    category,
                    fact_key,
                    json.dumps(value, ensure_ascii=True),
                    source,
                    confidence,
                    now,
                    expires_at,
                    now,
                ),
            )

    def list_facts(self, server_id: str, category: str | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT category, fact_key, value_json, source, confidence,
                   observed_at, expires_at, updated_at
            FROM memory_facts
            WHERE server_id = ?
              AND (expires_at IS NULL OR expires_at > ?)
        """
        parameters: list[Any] = [server_id, self._now()]
        if category:
            query += " AND category = ?"
            parameters.append(category)
        query += " ORDER BY category, fact_key"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "category": row["category"],
                "fact_key": row["fact_key"],
                "value": json.loads(row["value_json"]),
                "source": row["source"],
                "confidence": row["confidence"],
                "observed_at": row["observed_at"],
                "expires_at": row["expires_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def record_observation(self, server_id: str, source: str, payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO memory_observations(server_id, source, payload_json, observed_at) VALUES (?, ?, ?, ?)",
                (server_id, source, json.dumps(payload, ensure_ascii=True), self._now()),
            )