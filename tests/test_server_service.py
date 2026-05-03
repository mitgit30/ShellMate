from pathlib import Path

from backend.app.repositories.server_repository import SQLiteServerRepository
from backend.app.schemas.server import ServerCreate
from backend.app.services.server_service import ServerService


def test_create_server_registers_pem_based_server(tmp_path: Path) -> None:
    service = ServerService(
        server_repository=SQLiteServerRepository(tmp_path / "servers-test.db")
    )

    created = service.create_server(
        ServerCreate(
            id="prod-01",
            name="Production Server",
            host="54.210.123.45",
            port=22,
            username="ubuntu",
            private_key_path="C:/keys/prod-01.pem",
        )
    )

    assert created.id == "prod-01"
    assert len(service.list_servers()) == 1
