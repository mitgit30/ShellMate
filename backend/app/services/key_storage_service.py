from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backend.app.core.config import get_settings
from backend.app.core.exceptions import InvalidKeyUploadError
from backend.app.schemas.key import UploadedKeyResponse


class KeyStorageService:
    def __init__(self) -> None:
        self._settings = get_settings()

    async def store_uploaded_key(self, uploaded_file: UploadFile) -> UploadedKeyResponse:
        filename = uploaded_file.filename or ""
        if not filename.lower().endswith(".pem"):
            raise InvalidKeyUploadError("Only .pem SSH key files are supported.")

        content = await uploaded_file.read()
        if not content:
            raise InvalidKeyUploadError("Uploaded .pem file is empty.")

        storage_dir = self._settings.ssh_key_storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)

        stored_filename = f"{uuid4().hex}-{Path(filename).name}"
        stored_path = storage_dir / stored_filename
        stored_path.write_bytes(content)

        return UploadedKeyResponse(
            original_filename=filename,
            stored_filename=stored_filename,
            private_key_path=str(stored_path.resolve()),
        )
