from fastapi import APIRouter, HTTPException, status

from backend.app.api.dependencies import server_service, ssh_service
from backend.app.core.exceptions import (
    ServerAlreadyExistsError,
    ServerNotFoundError,
    SSHConnectionError,
)
from backend.app.schemas.server import ServerConnectionTestResponse, ServerCreate, ServerResponse

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("", response_model=list[ServerResponse])
def list_servers() -> list[ServerResponse]:
    return server_service.list_servers()


@router.post("", response_model=ServerResponse, status_code=status.HTTP_201_CREATED)
def create_server(payload: ServerCreate) -> ServerResponse:
    try:
        return server_service.create_server(payload)
    except ServerAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/{server_id}", response_model=ServerResponse)
def get_server(server_id: str) -> ServerResponse:
    try:
        return server_service.get_server(server_id)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{server_id}/test", response_model=ServerConnectionTestResponse)
def test_server_connection(server_id: str) -> ServerConnectionTestResponse:
    try:
        ssh_service.open_session(server_id)
        return ServerConnectionTestResponse(server_id=server_id, is_reachable=True)
    except ServerNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SSHConnectionError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
