from pathlib import Path

from fastapi import UploadFile

from backend.app.core.exceptions import (
    ServerAlreadyExistsError,
    ServerNotFoundError,
)
from backend.app.repositories.server_repository import ServerRepository
from backend.app.schemas.server import ServerCreate, ServerRecord, ServerResponse
from backend.app.services.key_storage_service import KeyStorageService


class ServerService:
    def __init__(
        self,
        server_repository: ServerRepository,
        key_storage_service: KeyStorageService | None = None,
    ) -> None:
        self._server_repository = server_repository
        self._key_storage_service = key_storage_service

    def list_servers(self) -> list[ServerResponse]:
        return [
            ServerResponse.from_record(record)
            for record in self._server_repository.list()
        ]

    def create_server(self, payload: ServerCreate) -> ServerResponse:
        existing_server = self._server_repository.get(payload.id)
        if existing_server is not None:
            raise ServerAlreadyExistsError(
                f"Server with id '{payload.id}' is already registered."
            )

        private_key_path = payload.private_key_path
        if payload.key_id and self._key_storage_service:
            private_key_path = str(self._key_storage_service.resolve_key_path(payload.key_id))
        if not private_key_path:
            raise ValueError("A valid SSH key is required.")

        record = ServerRecord(
            id=payload.id,
            name=payload.name,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            private_key_path=private_key_path,
        )
        self._server_repository.add(record)
        return ServerResponse.from_record(record)

    def get_server(self, server_id: str) -> ServerResponse:
        record = self._get_server_record(server_id)
        return ServerResponse.from_record(record)

    async def rotate_key(self, server_id: str, uploaded_file: UploadFile) -> ServerResponse:
        if self._key_storage_service is None:
            raise ValueError("Key storage is not configured.")

        record = self._get_server_record(server_id)
        new_key = await self._key_storage_service.store_uploaded_key(uploaded_file)
        new_path = self._key_storage_service.resolve_key_path(new_key.key_id)
        try:
            self._server_repository.update_key(server_id, str(new_path))
        except Exception:
            self._key_storage_service.delete_key(new_key.key_id)
            raise

        old_key_id = Path(record.private_key_path).name
        if old_key_id != new_key.key_id:
            try:
                self._key_storage_service.delete_key(old_key_id)
            except Exception:
                # The new key is active; an orphaned old key can be cleaned up
                # separately without making rotation appear to have failed.
                pass
        return self.get_server(server_id)

    def get_server_record(self, server_id: str) -> ServerRecord:
        return self._get_server_record(server_id)

    def _get_server_record(self, server_id: str) -> ServerRecord:
        record = self._server_repository.get(server_id)
        if record is None:
            raise ServerNotFoundError(f"Server with id '{server_id}' was not found.")
        return record
