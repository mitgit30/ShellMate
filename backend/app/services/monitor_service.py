from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from backend.app.db.database import Database
from backend.app.schemas.monitor import MonitorEvent, MonitorTask, MonitorTaskDetails


class MonitorService:
    """Persists safe, user-scoped summaries of agent executions."""

    def __init__(self, database_path: Path | None = None, database: Database | None = None) -> None:
        self._database = database or Database(None, database_path or Path("backend/data/servers.db"))
        self._database.initialize_schema()

    def start_task(self, user_id: str, session_id: str, server_id: str, user_request: str) -> str:
        task_id = uuid4().hex
        now = _now()
        with self._database.connect() as connection:
            connection.execute(
                """INSERT INTO agent_tasks
                (task_id, user_id, session_id, server_id, user_request, status, started_at)
                VALUES (?, ?, ?, ?, ?, 'running', ?)""",
                (task_id, user_id, session_id, server_id, user_request[:2000], now),
            )
            connection.commit()
        return task_id

    def record_event(self, task_id: str, event: dict) -> None:
        event_type = str(event.get("type", "unknown"))
        # Token chunks are response transport details, not useful monitor events.
        if event_type == "token":
            return
        step = _text(event.get("step"))
        skill_id = _text(event.get("skill_id"))
        tool_name = _text(event.get("tool_name"))
        command = _text(event.get("command"))
        iteration = event.get("iteration")
        if not isinstance(iteration, int):
            iteration = None
        detail = _text(event.get("detail") or event.get("reason"))
        exit_status = event.get("exit_status")
        if not isinstance(exit_status, int):
            exit_status = None

        with self._database.connect() as connection:
            current = connection.execute(
                "SELECT status, deployment_status FROM agent_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            connection.execute(
                """INSERT INTO agent_events
                (task_id, event_type, detail, skill_id, step, tool_name, command, iteration, exit_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (task_id, event_type, detail, skill_id, step, tool_name, command, iteration, exit_status, _now()),
            )
            updates: dict[str, object] = {}
            if skill_id:
                updates["current_skill"] = skill_id
            if step:
                updates["current_step"] = step
            if event_type == "error":
                updates.update(status="failed", error_message=detail or "Agent execution failed.")
                if (
                    skill_id == "deployment"
                    or (step and step.startswith("deployment"))
                    or (current and current["deployment_status"] == "in_progress")
                ):
                    updates["deployment_status"] = "failed"
            elif skill_id == "deployment" or (step and step.startswith("deployment")):
                updates["deployment_status"] = "in_progress"
            if event_type == "done" and current and current["status"] != "failed":
                updates["status"] = "completed"
                updates["completed_at"] = _now()
                if current["deployment_status"] == "in_progress":
                    updates["deployment_status"] = "completed"
            if updates:
                assignments = ", ".join(f"{key} = ?" for key in updates)
                connection.execute(
                    f"UPDATE agent_tasks SET {assignments} WHERE task_id = ?",
                    (*updates.values(), task_id),
                )
            connection.commit()

    def fail_task(self, task_id: str, message: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE agent_tasks
                SET status = 'failed', error_message = ?, completed_at = ?
                WHERE task_id = ?""",
                (message[:1000], _now(), task_id),
            )
            connection.commit()

    def complete_task(self, task_id: str) -> None:
        with self._database.connect() as connection:
            connection.execute(
                """UPDATE agent_tasks SET status = 'completed', completed_at = ?
                WHERE task_id = ? AND status = 'running'""",
                (_now(), task_id),
            )
            connection.commit()

    def list_tasks(self, user_id: str, server_id: str | None = None, limit: int = 25) -> list[MonitorTask]:
        with self._database.connect() as connection:
            if server_id:
                rows = connection.execute(
                    """SELECT * FROM agent_tasks WHERE user_id = ? AND server_id = ?
                    ORDER BY started_at DESC LIMIT ?""", (user_id, server_id, limit)
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT * FROM agent_tasks WHERE user_id = ?
                    ORDER BY started_at DESC LIMIT ?""", (user_id, limit)
                ).fetchall()
        return [self._task(row) for row in rows]

    def get_task(self, user_id: str, task_id: str) -> MonitorTaskDetails | None:
        with self._database.connect() as connection:
            task = connection.execute(
                "SELECT * FROM agent_tasks WHERE task_id = ? AND user_id = ?",
                (task_id, user_id),
            ).fetchone()
            if task is None:
                return None
            events = connection.execute(
                "SELECT * FROM agent_events WHERE task_id = ? ORDER BY event_id",
                (task_id,),
            ).fetchall()
        return MonitorTaskDetails(task=self._task(task), events=[self._event(row) for row in events])

    @staticmethod
    def _task(row) -> MonitorTask:
        return MonitorTask(
            task_id=row["task_id"], session_id=row["session_id"], server_id=row["server_id"],
            user_request=row["user_request"], status=row["status"],
            current_skill=row["current_skill"], current_step=row["current_step"],
            deployment_status=row["deployment_status"], started_at=row["started_at"],
            completed_at=row["completed_at"], error_message=row["error_message"],
        )

    @staticmethod
    def _event(row) -> MonitorEvent:
        return MonitorEvent(
            event_id=row["event_id"], task_id=row["task_id"], event_type=row["event_type"],
            detail=row["detail"], skill_id=row["skill_id"], step=row["step"],
            tool_name=row["tool_name"], exit_status=row["exit_status"], created_at=row["created_at"],
            command=row["command"], iteration=row["iteration"],
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
