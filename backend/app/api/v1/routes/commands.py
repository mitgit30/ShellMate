from fastapi import APIRouter, HTTPException

from backend.app.api.dependencies import ssh_service
from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError
from backend.app.schemas.command import CommandExecutionRequest, CommandExecutionResponse

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("/execute", response_model=CommandExecutionResponse)
def execute_command(payload: CommandExecutionRequest) -> CommandExecutionResponse:
    try:
        return ssh_service.execute_command(
            server_id=payload.server_id,
            command=payload.command,
        )
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SSHConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
