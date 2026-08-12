from datetime import datetime

from pydantic import BaseModel


class MonitorTask(BaseModel):
    task_id: str
    session_id: str
    server_id: str
    user_request: str
    status: str
    current_skill: str | None = None
    current_step: str | None = None
    deployment_status: str = "not_applicable"
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None


class MonitorEvent(BaseModel):
    event_id: int
    task_id: str
    event_type: str
    detail: str | None = None
    skill_id: str | None = None
    step: str | None = None
    tool_name: str | None = None
    command: str | None = None
    iteration: int | None = None
    exit_status: int | None = None
    created_at: datetime


class MonitorTaskDetails(BaseModel):
    task: MonitorTask
    events: list[MonitorEvent]
