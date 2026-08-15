"""SQLite-backed server memory facade."""
from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Any

from backend.app.db.database import Database
from src.memory.sqlite_store import SQLiteMemoryStore

logger = logging.getLogger(__name__)


class MemoryManager:
    """Application-facing memory API backed by SQLite."""

    def __init__(
        self,
        database_path: Path | None = None,
        base_dir: Path | None = None,
        historical_memory_path: Path | None = None,
        historical_store: Any | None = None,
        database: Database | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        if database_path is None:
            database_path = (base_dir / "memory.db") if base_dir else project_root / "backend" / "data" / "memory.db"
        self._store = SQLiteMemoryStore(database_path, database=database)
        self._historical_store = historical_store
        self._retrieval_events: dict[str, list[dict[str, str | int | None]]] = defaultdict(list)
        self._retrieval_events_lock = RLock()
        if self._historical_store is None and historical_memory_path is not None:
            self._historical_store = self._create_historical_store(historical_memory_path)

    @staticmethod
    def _create_historical_store(path: Path):
        from src.memory.vector_store import HistoricalMemoryStore

        return HistoricalMemoryStore(path)

    def read_handoff(self, server_id: str) -> str:
        return self._store.get_document(server_id, "handoff")

    def write_handoff(self, server_id: str, content: str) -> None:
        self._store.save_document(server_id, "handoff", self._trim_lines(content, limit=50))

    def read_server_facts(self, server_id: str) -> str:
        grouped: dict[str, list[str]] = {}
        for fact in self._store.list_facts(server_id):
            category = str(fact["category"])
            grouped.setdefault(category, []).append(str(fact["value"]))
        return self._render_sections(grouped)

    def update_server_facts(self, server_id: str, new_facts: dict[str, list[str]]) -> None:
        for category, lines in new_facts.items():
            for line in lines:
                cleaned = str(line).strip()
                if not cleaned:
                    continue

                fact_key = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
                self._store.upsert_fact(
                    server_id=server_id,
                    category=category,
                    fact_key=fact_key,
                    value=cleaned,
                    source="context_extractor",
                )

    def read_session(self, server_id: str) -> str:
        return self._store.get_document(server_id, "session")

    def write_session(self, server_id: str, content: str) -> None:
        self._store.save_document(server_id, "session", content.strip())

    def latest_path(self, server_id: str) -> str | None:
        for content in (self.read_session(server_id), self.read_handoff(server_id), self.read_server_facts(server_id)):
            for line in reversed(content.splitlines()):
                parsed = self._parse_path_line(line)
                if parsed:
                    return parsed[1]
        return None

    def latest_port(self, server_id: str) -> int | None:
        for content in (self.read_session(server_id), self.read_handoff(server_id), self.read_server_facts(server_id)):
            for line in reversed(content.splitlines()):
                parsed = self._parse_port_line(line)
                if parsed is not None:
                    return parsed
        return None

    def record_observation(self, server_id: str, source: str, payload: dict[str, Any]) -> None:
        self._store.record_observation(server_id, source, payload)

    def record_historical_memory(
        self,
        server_id: str,
        summary: str,
        source: str,
        session_id: str | None = None,
    ) -> None:
        if self._historical_store is None:
            return
        try:
            self._historical_store.add_summary(
                server_id=server_id,
                summary=summary,
                source=source,
                session_id=session_id,
            )
        except Exception:
            # Historical indexing must never break the primary agent turn.
            logger.warning(
                "historical_memory_index_failed server_id=%s source=%s session_id=%s",
                server_id,
                source,
                session_id or "-",
                exc_info=True,
            )
            return

    def search_historical_memory(
        self,
        server_id: str,
        query: str,
        limit: int = 3,
        date_from: date | None = None,
        date_to: date | None = None,
        session_id: str | None = None,
    ) -> list[str]:
        if self._historical_store is None:
            return []
        try:
            results = self._historical_store.search(
                server_id=server_id,
                query=query,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
            )
            if session_id:
                date_label = ""
                if date_from and date_to:
                    date_label = date_from.isoformat() if date_from == date_to else f"{date_from.isoformat()} to {date_to.isoformat()}"
                detail = f"ChromaDB retrieved {len(results)} historical record(s)"
                if date_label:
                    detail += f" for {date_label}"
                elif not results:
                    detail += " matching this request"
                self._queue_retrieval_event(
                    session_id,
                    {
                        "type": "historical_memory_retrieved",
                        "source": "ChromaDB",
                        "matches": len(results),
                        "date_from": date_from.isoformat() if date_from else None,
                        "date_to": date_to.isoformat() if date_to else None,
                        "detail": detail + ".",
                    },
                )
            return results
        except Exception:
            # A missing embedding model or unavailable Chroma must not block chat.
            logger.warning(
                "historical_memory_search_failed server_id=%s date_from=%s date_to=%s",
                server_id,
                date_from or "-",
                date_to or "-",
                exc_info=True,
            )
            if session_id:
                self._queue_retrieval_event(
                    session_id,
                    {
                        "type": "historical_memory_unavailable",
                        "source": "ChromaDB",
                        "matches": 0,
                        "detail": "ChromaDB historical memory was unavailable for this request.",
                    },
                )
            return []

    def consume_historical_retrieval_events(self, session_id: str) -> list[dict]:
        """Return and clear retrieval events generated during the current turn."""
        with self._retrieval_events_lock:
            return list(self._retrieval_events.pop(session_id, []))

    def _queue_retrieval_event(self, session_id: str, event: dict) -> None:
        with self._retrieval_events_lock:
            self._retrieval_events[session_id].append(event)

    @staticmethod
    def _trim_lines(content: str, limit: int) -> str:
        lines = [line.rstrip() for line in content.splitlines() if line.strip()]
        return "\n".join(lines[-limit:])

    @staticmethod
    def _render_sections(sections: dict[str, list[str]]) -> str:
        ordered_sections = ("Paths", "Packages", "Ports", "Containers")
        blocks: list[str] = []
        for section in ordered_sections:
            lines = sections.get(section, [])
            if lines:
                blocks.append(f"## {section}\n" + "\n".join(lines))
        for section, lines in sections.items():
            if section in ordered_sections or not lines:
                continue
            blocks.append(f"## {section}\n" + "\n".join(lines))
        return "\n\n".join(blocks)

    @staticmethod
    def _parse_sections(content: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if line.startswith("## "):
                current = line[3:].strip()
                sections.setdefault(current, [])
                continue
            if current and line.strip():
                sections[current].append(line.strip())
        return sections

    @staticmethod
    def _parse_path_line(line: str) -> tuple[str, str] | None:
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            return None
        name, value = stripped[2:].split(":", 1)
        path = value.strip()
        if path.startswith("/") or path.startswith("~/"):
            return name.strip(), path
        return None

    @staticmethod
    def _parse_port_line(line: str) -> int | None:
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            return None
        name, _ = stripped[2:].split(":", 1)
        if name.strip().isdigit():
            value = int(name.strip())
            if 1 <= value <= 65535:
                return value
        return None
