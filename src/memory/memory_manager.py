"""SQLite-backed server memory facade."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

from src.memory.sqlite_store import SQLiteMemoryStore


class MemoryManager:
    """Application-facing memory API backed by SQLite."""

    def __init__(
        self,
        database_path: Path | None = None,
        base_dir: Path | None = None,
        historical_memory_path: Path | None = None,
        historical_store: Any | None = None,
    ) -> None:
        project_root = Path(__file__).resolve().parents[2]
        if database_path is None:
            database_path = (base_dir / "memory.db") if base_dir else project_root / "backend" / "data" / "memory.db"
        self._store = SQLiteMemoryStore(database_path)
        self._historical_store = historical_store
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
            return

    def search_historical_memory(
        self,
        server_id: str,
        query: str,
        limit: int = 3,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[str]:
        if self._historical_store is None:
            return []
        try:
            return self._historical_store.search(
                server_id=server_id,
                query=query,
                limit=limit,
                date_from=date_from,
                date_to=date_to,
            )
        except Exception:
            # A missing embedding model or unavailable Chroma must not block chat.
            return []

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
