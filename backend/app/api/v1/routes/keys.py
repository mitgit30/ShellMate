from fastapi import APIRouter, File, HTTPException, UploadFile, status

from backend.app.api.dependencies import key_storage_service
from backend.app.core.exceptions import InvalidKeyUploadError
from backend.app.schemas.key import UploadedKeyResponse

router = APIRouter(prefix="/keys", tags=["keys"])


@router.post("/upload", response_model=UploadedKeyResponse, status_code=status.HTTP_201_CREATED)
async def upload_private_key(private_key: UploadFile = File(...)) -> UploadedKeyResponse:
    try:
        return await key_storage_service.store_uploaded_key(private_key)
    except InvalidKeyUploadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
