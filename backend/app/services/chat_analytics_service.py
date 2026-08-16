import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.db.database import Database


class ChatAnalyticsService:
    """Read-only account analytics for persisted conversations."""

    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/servers.db"))
        if database is None:
            self._database.initialize_schema()

    def count_user_messages(self, user_id: str, days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._database.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) AS count FROM chat_messages
                WHERE user_id = ? AND role = 'user' AND created_at >= ?""",
                (user_id, cutoff.isoformat()),
            ).fetchone()
        return int(row["count"]) if row else 0


def requested_chat_window(message: str) -> int | None:
    lowered = message.lower()
    if not any(term in lowered for term in ("chat", "conversation", "message")):
        return None
    match = re.search(r"(?:last|past|previous)\s+(\d+)\s+days?", lowered)
    if match:
        return max(1, min(int(match.group(1)), 3650))
    if "yesterday" in lowered:
        return 1
    return None


def is_chat_count_request(message: str) -> bool:
    lowered = message.lower()
    return requested_chat_window(message) is not None and any(
        term in lowered for term in ("how many", "count", "number")
    )
