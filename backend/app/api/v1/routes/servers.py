from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.app.api.dependencies import server_service, ssh_service
from backend.app.core.exceptions import (
    InvalidKeyUploadError,
    ServerAlreadyExistsError,
    ServerNotFoundError,
    SSHConnectionError,
)
from backend.app.schemas.server import ServerConnectionTestResponse, ServerCreate, ServerResponse
from backend.app.core.auth import get_current_user
from backend.app.repositories.user_repository import User

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("", response_model=list[ServerResponse])
def list_servers(user: User = Depends(get_current_user)) -> list[ServerResponse]:
    return server_service.list_servers(user.id)


@router.post("", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
def create_server(payload: ServerCreate, user: User = Depends(get_current_user)) -> ServerResponse:
    try:
        return server_service.create_server(payload, user.id)
    except ServerAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (InvalidKeyUploadError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: str, user: User = Depends(get_current_user)) -> ServerResponse:
    try:
        return server_service.get_server(server_id, user.id)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{server_id}/test", response_model=ServerConnectionTestResponse)
def test_server_connection(server_id: str, user: User = Depends(get_current_user)) -> ServerConnectionTestResponse:
    try:
        server_service.get_server_record(server_id, user.id)
        ssh_service.open_session(server_id)
        return ServerConnectionTestResponse(server_id=server_id, is_reachable=True)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SSHConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/{server_id}/key", response_model=ServerResponse)
async def rotate_server_key(
    server_id: str,
    private_key: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> ServerResponse:
    try:
        return await server_service.rotate_key(server_id, private_key, user.id)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidKeyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
