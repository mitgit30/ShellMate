from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.db.database import Database


class ChatHistoryService:
    """Persists user-owned chat messages in the shared application database."""

    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/servers.db"))
        if database is None:
            self._database.initialize_schema()

    def append(self, user_id: str, session_id: str, server_id: str, role: str, content: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO chat_messages
                (user_id, session_id, server_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, session_id, server_id, role, content, _now()),
            )
            connection.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ? AND user_id = ?",
                (_now(), session_id, user_id),
            )
            connection.commit()

    def ensure_session(self, user_id: str, session_id: str, server_id: str, title: str = "New chat") -> None:
        now = _now()
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO chat_sessions
                (session_id, user_id, server_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO NOTHING""",
                (session_id, user_id, server_id, title[:120], now, now),
            )
            connection.commit()

    def create_session(self, user_id: str, server_id: str, title: str = "New chat") -> dict:
        session_id = f"chat-{uuid4().hex}"
        self.ensure_session(user_id, session_id, server_id, title)
        return self.get_session(user_id, session_id, server_id)

    def list_sessions(self, user_id: str, server_id: str) -> list[dict]:
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO chat_sessions
                (session_id, user_id, server_id, title, created_at, updated_at)
                SELECT session_id, user_id, server_id, 'Previous chat',
                       MIN(created_at), MAX(created_at)
                FROM chat_messages
                WHERE user_id = ? AND server_id = ?
                GROUP BY session_id, user_id, server_id
                ON CONFLICT(session_id) DO NOTHING""",
                (user_id, server_id),
            )
            rows = connection.execute(
                """SELECT session_id, server_id, title, created_at, updated_at
                FROM chat_sessions WHERE user_id = ? AND server_id = ?
                ORDER BY updated_at DESC""",
                (user_id, server_id),
            ).fetchall()
            connection.commit()
        return [_serialize_session(dict(row)) for row in rows]

    def get_session(self, user_id: str, session_id: str, server_id: str) -> dict:
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT session_id, server_id, title, created_at, updated_at
                FROM chat_sessions WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (user_id, session_id, server_id),
            ).fetchone()
        if row is None:
            raise ValueError("Chat session was not found.")
        return _serialize_session(dict(row))

    def set_title(self, user_id: str, session_id: str, server_id: str, title: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE chat_sessions SET title = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (title[:120], _now(), user_id, session_id, server_id),
            )
            connection.commit()

    def delete_session(self, user_id: str, session_id: str, server_id: str) -> bool:
        with self._database.connect() as connection:
            exists = connection.execute(
                """SELECT 1 FROM chat_sessions
                WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (user_id, session_id, server_id),
            ).fetchone()
            if exists is None:
                return False
            connection.execute(
                """DELETE FROM chat_messages
                WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (user_id, session_id, server_id),
            )
            connection.execute(
                "DELETE FROM chat_sessions WHERE user_id = ? AND session_id = ? AND server_id = ?",
                (user_id, session_id, server_id),
            )
            connection.commit()
        return True

    def list_messages(self, user_id: str, session_id: str, server_id: str) -> list[dict]:
        with self._database.connect() as connection:
            rows = connection.execute(
                """SELECT role, content, created_at FROM chat_messages
                WHERE user_id = ? AND session_id = ? AND server_id = ?
                ORDER BY message_id""",
                (user_id, session_id, server_id),
            ).fetchall()
        return [_serialize_message(dict(row)) for row in rows]

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize_session(session: dict) -> dict:
    for field in ("created_at", "updated_at"):
        session[field] = _timestamp_to_iso(session.get(field))
    return session


def _serialize_message(message: dict) -> dict:
    message["created_at"] = _timestamp_to_iso(message.get("created_at"))
    return message


def _timestamp_to_iso(value) -> str:
    """Return a consistent ISO-8601 string for SQLite and PostgreSQL values."""
    if isinstance(value, datetime):
        normalized = value
        if normalized.tzinfo is None:
            normalized = normalized.replace(tzinfo=timezone.utc)
        else:
            normalized = normalized.astimezone(timezone.utc)
        return normalized.isoformat()
    return str(value) if value is not None else ""
