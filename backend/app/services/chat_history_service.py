import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class ChatHistoryService:
    """Persists user-owned chat messages in the shared application database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def append(self, user_id: str, session_id: str, server_id: str, role: str, content: str) -> None:
        with self._connect() as connection:
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
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO chat_sessions
                (session_id, user_id, server_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, user_id, server_id, title[:120], now, now),
            )
            connection.commit()

    def create_session(self, user_id: str, server_id: str, title: str = "New chat") -> dict:
        session_id = f"chat-{uuid4().hex}"
        self.ensure_session(user_id, session_id, server_id, title)
        return self.get_session(user_id, session_id, server_id)

    def list_sessions(self, user_id: str, server_id: str) -> list[dict]:
        with self._connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO chat_sessions
                (session_id, user_id, server_id, title, created_at, updated_at)
                SELECT session_id, user_id, server_id, 'Previous chat',
                       MIN(created_at), MAX(created_at)
                FROM chat_messages
                WHERE user_id = ? AND server_id = ?
                GROUP BY session_id, user_id, server_id""",
                (user_id, server_id),
            )
            rows = connection.execute(
                """SELECT session_id, server_id, title, created_at, updated_at
                FROM chat_sessions WHERE user_id = ? AND server_id = ?
                ORDER BY updated_at DESC""",
                (user_id, server_id),
            ).fetchall()
            connection.commit()
        return [dict(row) for row in rows]

    def get_session(self, user_id: str, session_id: str, server_id: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT session_id, server_id, title, created_at, updated_at
                FROM chat_sessions WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (user_id, session_id, server_id),
            ).fetchone()
        if row is None:
            raise ValueError("Chat session was not found.")
        return dict(row)

    def set_title(self, user_id: str, session_id: str, server_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE chat_sessions SET title = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ? AND server_id = ?""",
                (title[:120], _now(), user_id, session_id, server_id),
            )
            connection.commit()

    def delete_session(self, user_id: str, session_id: str, server_id: str) -> bool:
        with self._connect() as connection:
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
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT role, content, created_at FROM chat_messages
                WHERE user_id = ? AND session_id = ? AND server_id = ?
                ORDER BY message_id""",
                (user_id, session_id, server_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS chat_messages (
                    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_chat_messages_session
                ON chat_messages(user_id, session_id, server_id, message_id)"""
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
