import os
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

        max_size = self._settings.ssh_key_max_size_bytes
        content = await uploaded_file.read(max_size + 1)
        if not content:
            raise InvalidKeyUploadError("Uploaded .pem file is empty.")
        if len(content) > max_size:
            raise InvalidKeyUploadError(
                f"SSH key file is too large. Maximum size is {max_size // 1024} KB."
            )
        if not self._is_private_key(content):
            raise InvalidKeyUploadError(
                "The uploaded file does not contain a supported PEM private key."
            )

        storage_dir = self._settings.ssh_key_storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        self._restrict_permissions(storage_dir, 0o700)

        # Do not preserve the user-provided filename in storage. It is not needed
        # for SSH and may expose identifying information in the filesystem.
        stored_filename = f"{uuid4().hex}.pem"
        stored_path = storage_dir / stored_filename
        try:
            with stored_path.open("xb") as key_file:
                key_file.write(content)
                key_file.flush()
                os.fsync(key_file.fileno())
            self._restrict_permissions(stored_path, 0o600)
        except OSError as exc:
            stored_path.unlink(missing_ok=True)
            raise InvalidKeyUploadError("The SSH key could not be stored securely.") from exc

        return UploadedKeyResponse(
            original_filename=filename,
            key_id=stored_filename,
        )

    def resolve_key_path(self, key_id: str) -> Path:
        """Resolve an opaque key ID without allowing path traversal."""
        if not key_id or Path(key_id).name != key_id or "/" in key_id or "\\" in key_id:
            raise InvalidKeyUploadError("Invalid SSH key identifier.")
        key_path = self._settings.ssh_key_storage_dir / key_id
        if not key_path.is_file():
            raise InvalidKeyUploadError("SSH key was not found.")
        return key_path.resolve()

    def delete_key(self, key_id: str) -> None:
        key_path = self.resolve_key_path(key_id)
        try:
            key_path.unlink()
        except OSError as exc:
            raise InvalidKeyUploadError("SSH key could not be deleted.") from exc

    @staticmethod
    def _is_private_key(content: bytes) -> bool:
        normalized = content.lstrip()
        return normalized.startswith(b"-----BEGIN ") and b"PRIVATE KEY-----" in normalized.split(
            b"\n", 1
        )[0]

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            # Windows does not expose Unix permission bits. The container/Linux
            # deployment enforces these permissions; upload must remain portable.
            pass
