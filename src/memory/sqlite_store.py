"""Persistence for ShellMate server memory."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.db.database import Database

SCHEMA_VERSION = 1


class SQLiteMemoryStore:
    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/memory.db"))
        if database is None:
            self._database.initialize_schema()

    def _connect(self):
        return self._database.connect()

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
