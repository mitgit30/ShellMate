from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.api.dependencies import key_storage_service, server_service
from backend.app.core.exceptions import InvalidKeyUploadError
from backend.app.schemas.key import UploadedKeyResponse

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post("/upload", response_model=UploadedKeyResponse, status_code=status.HTTP_201_CREATED)
async def upload_private_key(private_key: UploadFile = File(...)) -> UploadedKeyResponse:
    try:
        return await key_storage_service.store_uploaded_key(private_key)
    except InvalidKeyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_private_key(key_id: str) -> None:
    if any(server.key_id == key_id for server in server_service.list_servers()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="SSH key is still attached to a registered server. Rotate or remove the server first.",
        )
    try:
        key_storage_service.delete_key(key_id)
    except InvalidKeyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
