from fastapi import APIRouter, HTTPException, status

from backend.app.api.dependencies import ssh_service
from backend.app.core.exceptions import SSHConnectionError, ServerNotFoundError
from backend.app.schemas.session import SSHSessionConnectRequest, SSHSessionResponse

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SSHSessionResponse, status_code=status.HTTP_201_CREATED)
def open_session(payload: SSHSessionConnectRequest) -> SSHSessionResponse:
    try:
        return ssh_service.open_session(payload.server_id)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SSHConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
