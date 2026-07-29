
from pathlib import Path

from src.memory.memory_manager import MemoryManager


def test_memory_manager_persists_documents_and_facts(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"
    manager = MemoryManager(database_path=database_path)

    manager.write_handoff("server-1", "## Pending\n- deploy the app")
    manager.write_session("server-1", "## Active Paths\n- app: /srv/app\n## Active Ports\n- 3000: free")
    manager.update_server_facts(
        "server-1",
        {"Paths": ["- app: /srv/app"], "Ports": ["- 3000: free"]},
    )

    reopened = MemoryManager(database_path=database_path)
    assert "deploy the app" in reopened.read_handoff("server-1")
    assert reopened.latest_path("server-1") == "/srv/app"
    assert reopened.latest_port("server-1") == 3000
    assert "Paths" in reopened.read_server_facts("server-1")