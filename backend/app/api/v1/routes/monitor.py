from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.dependencies import monitor_service
from backend.app.core.auth import get_current_user
from backend.app.repositories.user_repository import User
from backend.app.schemas.monitor import MonitorTask, MonitorTaskDetails

router = APIRouter(prefix="/monitor", tags=["monitor"])


@router.get("/tasks", response_model=list[MonitorTask])
def list_monitor_tasks(user: User = Depends(get_current_user)) -> list[MonitorTask]:
    return monitor_service.list_tasks(user.id)


@router.get("/tasks/{task_id}", response_model=MonitorTaskDetails)
def get_monitor_task(task_id: str, user: User = Depends(get_current_user)) -> MonitorTaskDetails:
    result = monitor_service.get_task(user.id, task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Monitoring task was not found.")
    return result
