
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from backend.app.db.database import Database
from src.runtime.config import get_runtime_settings


class HistoricalMemoryStore:

    _MAX_CONTENT_LENGTH = 4_000

    def __init__(
        self,
        persist_directory: Path,
        database: Database | None = None,
    ) -> None:
        self._persist_directory = persist_directory
        self._database = database
        self._store = None

    @property
    def backend_name(self) -> str:
        return "PostgreSQL pgvector" if self._uses_postgres else "ChromaDB"

    @property
    def _uses_postgres(self) -> bool:
        return bool(self._database and self._database.is_postgres)

    def _get_store(self):
        if self._store is not None:
            return self._store

        from langchain_ollama import OllamaEmbeddings

        settings = get_runtime_settings()
        if not settings.ollama_api_key:
            raise RuntimeError(
                "OLLAMA_API_KEY is required for Ollama Cloud embeddings."
            )
        client_kwargs = {
            "headers": {
                "Authorization": f"Bearer {settings.ollama_api_key}",
            }
        }
        embeddings = OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
            client_kwargs=client_kwargs,
        )
        if self._uses_postgres:
            self._store = self._create_pgvector_store(embeddings)
        else:
            from langchain_chroma import Chroma

            self._store = Chroma(
                collection_name="shellmate_historical_memory",
                embedding_function=embeddings,
                persist_directory=str(self._persist_directory),
            )
        return self._store

    def _create_pgvector_store(self, embeddings: Any):
        if not self._database:
            raise RuntimeError("PostgreSQL vector storage requires a database configuration.")

        
        with self._database.connect() as connection:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector")

        from langchain_postgres import PGVector

        database_url = self._database.engine.url.render_as_string(hide_password=False)
        return PGVector(
            embeddings=embeddings,
            collection_name="shellmate_historical_memory",
            connection=database_url,
            use_jsonb=True,
        )

    def add_summary(
        self,
        server_id: str,
        summary: str,
        source: str,
        session_id: str | None = None,
    ) -> None:
        content = self._sanitize(summary)
        if not content:
            return

        observed_at = datetime.now(timezone.utc).isoformat()
        record_id = hashlib.sha256(
            f"{server_id}:{source}:{content}".encode("utf-8")
        ).hexdigest()
        self._get_store().add_texts(
            texts=[content],
            metadatas=[
                {
                    "server_id": server_id,
                    "source": source,
                    "session_id": session_id or "",
                    "observed_at": observed_at,
                    "observed_date": observed_at[:10],
                }
            ],
            ids=[record_id],
        )

    def search(
        self,
        server_id: str,
        query: str,
        limit: int = 3,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[str]:
        cleaned_query = query.strip()
        if not cleaned_query:
            return []

        results = self._get_store().similarity_search(
            cleaned_query,
            k=max(1, min(limit * 10, 50)),
            filter={"server_id": server_id},
        )
        if date_from or date_to:
            results = [
                document
                for document in results
                if self._matches_date_range(document.metadata, date_from, date_to)
            ]
        return [document.page_content for document in results[:limit]]

    @staticmethod
    def _matches_date_range(
        metadata: dict,
        date_from: date | None,
        date_to: date | None,
    ) -> bool:
        observed_value = metadata.get("observed_date") or metadata.get("observed_at", "")
        try:
            observed_date = date.fromisoformat(str(observed_value)[:10])
        except ValueError:
            return False
        if date_from and observed_date < date_from:
            return False
        if date_to and observed_date > date_to:
            return False
        return True

    @classmethod
    def _sanitize(cls, content: str) -> str:
        sanitized = content.strip()
        sanitized = re.sub(
            r"-----BEGIN [^-]*PRIVATE KEY-----.+?-----END [^-]*PRIVATE KEY-----",
            "[REDACTED PRIVATE KEY]",
            sanitized,
            flags=re.DOTALL | re.IGNORECASE,
        )
        sanitized = re.sub(
            r"(?i)\b(password|passwd|token|secret|api[_ -]?key)\s*[:=]\s*\S+",
            r"\1=[REDACTED]",
            sanitized,
        )
        return sanitized[: cls._MAX_CONTENT_LENGTH]
