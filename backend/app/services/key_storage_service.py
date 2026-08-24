

from __future__ import annotations

import logging
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from fastapi import UploadFile

from backend.app.core.config import get_settings
from backend.app.core.exceptions import InvalidKeyUploadError
from backend.app.schemas.key import UploadedKeyResponse

logger = logging.getLogger(__name__)


class KeyStorageService:
    _KEY_VAULT_NAME_PATTERN = re.compile(r"^[0-9a-zA-Z-]{1,127}$")

    def __init__(self) -> None:
        self._settings = get_settings()
        self._key_vault_client = None

    @property
    def uses_key_vault(self) -> bool:
        return bool(self._settings.key_vault_url)

    async def store_uploaded_key(self, uploaded_file: UploadFile) -> UploadedKeyResponse:
        filename = uploaded_file.filename or ""
        if not filename.lower().endswith(".pem"):
            raise InvalidKeyUploadError("Only .pem SSH key files are supported.")

        content = await self._read_and_validate(uploaded_file)
        key_id = self._store_in_key_vault(content) if self.uses_key_vault else self._store_locally(content)
        return UploadedKeyResponse(original_filename=filename, key_id=key_id)

    def validate_key_reference(self, key_id: str) -> str:
        """Validate an uploaded key ID before associating it with a server."""
        if self.uses_key_vault:
            if not self._is_key_vault_name(key_id):
                raise InvalidKeyUploadError("Invalid SSH key identifier.")
            try:
                self._get_key_vault_client().get_secret(key_id)
            except Exception as exc:
                _log_key_vault_error("validate_secret", key_id, exc)
                raise InvalidKeyUploadError("SSH key was not found.") from exc
            return key_id

        return self.resolve_key_path(key_id).name

    def storage_backend_for(self, key_reference: str) -> str:
        """Return a safe backend label for audit logs."""
        if self.uses_key_vault and not self._looks_like_local_key(key_reference):
            return "azure_key_vault"
        return "local_file"

    def resolve_key_path(self, key_id: str) -> Path:
        if not self._is_safe_local_identifier(key_id):
            raise InvalidKeyUploadError("Invalid SSH key identifier.")
        key_path = self._settings.ssh_key_storage_dir / key_id
        if not key_path.is_file():
            raise InvalidKeyUploadError("SSH key was not found.")
        return key_path.resolve()

    @contextmanager
    def materialize_key(self, key_reference: str) -> Iterator[Path]:
        if not self.uses_key_vault or self._looks_like_local_key(key_reference):
            yield self._resolve_legacy_local_path(key_reference)
            return

        content = self._get_key_vault_value(key_reference).encode("utf-8")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="shellmate-ssh-",
                suffix=".pem",
                delete=False,
            ) as key_file:
                key_file.write(content)
                key_file.flush()
                os.fsync(key_file.fileno())
                temporary_path = Path(key_file.name)
            self._restrict_permissions(temporary_path, 0o600)
            yield temporary_path
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def delete_key(self, key_id: str) -> None:
        if self.uses_key_vault and not self._looks_like_local_key(key_id):
            if not self._is_key_vault_name(key_id):
                raise InvalidKeyUploadError("Invalid SSH key identifier.")
            try:
                self._get_key_vault_client().begin_delete_secret(key_id)
            except Exception as exc:
                _log_key_vault_error("delete_secret", key_id, exc)
                raise InvalidKeyUploadError("SSH key could not be deleted.") from exc
            logger.info("ssh_key_deleted backend=azure_key_vault key_id=%s", key_id)
            return

        key_path = self._resolve_legacy_local_path(key_id)
        try:
            key_path.unlink()
        except OSError as exc:
            raise InvalidKeyUploadError("SSH key could not be deleted.") from exc

    async def _read_and_validate(self, uploaded_file: UploadFile) -> bytes:
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
        return content

    def _store_locally(self, content: bytes) -> str:
        storage_dir = self._settings.ssh_key_storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        self._restrict_permissions(storage_dir, 0o700)

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
        return stored_filename

    def _store_in_key_vault(self, content: bytes) -> str:
        try:
            key_value = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidKeyUploadError("The SSH key must contain valid PEM text.") from exc

        key_id = f"{self._settings.key_vault_secret_prefix}-{uuid4().hex}"
        try:
            self._get_key_vault_client().set_secret(key_id, key_value)
        except Exception as exc:
            _log_key_vault_error("set_secret", key_id, exc)
            raise InvalidKeyUploadError("The SSH key could not be stored in Azure Key Vault.") from exc
        logger.info("ssh_key_stored backend=azure_key_vault key_id=%s", key_id)
        return key_id

    def _get_key_vault_value(self, key_id: str) -> str:
        if not self._is_key_vault_name(key_id):
            raise InvalidKeyUploadError("Invalid SSH key identifier.")
        try:
            value = self._get_key_vault_client().get_secret(key_id).value
        except Exception as exc:
            _log_key_vault_error("get_secret", key_id, exc)
            raise InvalidKeyUploadError("SSH key was not found in Azure Key Vault.") from exc
        if not value:
            raise InvalidKeyUploadError("SSH key value is empty.")
        logger.info("ssh_key_retrieved backend=azure_key_vault key_id=%s", key_id)
        return value

    def _get_key_vault_client(self):
        if self._key_vault_client is None:
            if not self._settings.key_vault_url:
                raise InvalidKeyUploadError("Azure Key Vault is not configured.")
            from azure.keyvault.secrets import SecretClient

            if self._settings.azure_use_managed_identity:
                from azure.identity import ManagedIdentityCredential

                credential = ManagedIdentityCredential()
                credential_mode = "managed_identity"
            else:
                from azure.identity import DefaultAzureCredential

                # Local mode supports Azure CLI, environment credentials, or
                # another developer credential, but never probes managed
                # identity outside Azure hosting.
                credential = DefaultAzureCredential(
                    exclude_managed_identity_credential=True,
                )
                credential_mode = "local_default_without_managed_identity"

            self._key_vault_client = SecretClient(
                vault_url=self._settings.key_vault_url,
                credential=credential,
            )
            logger.info("azure_key_vault_client_created credential=%s", credential_mode)
        return self._key_vault_client

    def _resolve_legacy_local_path(self, key_reference: str) -> Path:
        if Path(key_reference).is_absolute():
            key_path = Path(key_reference)
            if not key_path.is_file():
                raise InvalidKeyUploadError("SSH key was not found.")
            return key_path.resolve()
        return self.resolve_key_path(key_reference)

    @staticmethod
    def _looks_like_local_key(key_reference: str) -> bool:
        return (
            key_reference.lower().endswith(".pem")
            or "/" in key_reference
            or "\\" in key_reference
        )

    @classmethod
    def _is_key_vault_name(cls, key_id: str) -> bool:
        return bool(cls._KEY_VAULT_NAME_PATTERN.fullmatch(key_id or ""))

    @staticmethod
    def _is_safe_local_identifier(key_id: str) -> bool:
        return bool(key_id) and Path(key_id).name == key_id and "/" not in key_id and "\\" not in key_id

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
            #no any windows error
            pass


def _log_key_vault_error(operation: str, key_id: str, error: Exception) -> None:
    """Write useful Azure diagnostics without dumping SDK tracebacks at INFO."""
    status_code = getattr(error, "status_code", None)
    error_code = getattr(error, "error_code", None)
    message = " ".join(str(error).split())[:500]
    logger.error(
        "azure_key_vault_operation_failed operation=%s key_id=%s status_code=%s error_code=%s message=%s",
        operation,
        key_id,
        status_code or "-",
        error_code or "-",
        message or type(error).__name__,
    )
    logger.debug(
        "azure_key_vault_operation_trace operation=%s key_id=%s",
        operation,
        key_id,
        exc_info=error,
    )
