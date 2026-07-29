from pathlib import Path

from src.memory.memory_manager import MemoryManager
from src.memory.vector_store import HistoricalMemoryStore
from src.runtime.prompt_composer import PromptComposer


class FakeHistoricalStore:
    def __init__(self) -> None:
        self.added: list[dict] = []

    def add_summary(self, **kwargs) -> None:
        self.added.append(kwargs)

    def search(self, **kwargs) -> list[str]:
        return ["Previous deployment failed because port 8080 was occupied."]


def test_historical_memory_is_server_scoped_and_retrieved_for_history_queries(tmp_path: Path) -> None:
    fake_store = FakeHistoricalStore()
    manager = MemoryManager(
        database_path=tmp_path / "memory.db",
        historical_store=fake_store,
    )

    manager.record_historical_memory(
        server_id="server-1",
        summary="Previous deployment failed.",
        source="test",
        session_id="session-1",
    )

    prompt = PromptComposer.build_memory_block(
        server_id="server-1",
        memory_manager=manager,
        historical_query="What happened during the previous deployment?",
    )

    assert "RELEVANT HISTORICAL SERVER CONTEXT" in prompt
    assert fake_store.added[0]["server_id"] == "server-1"


def test_non_historical_queries_do_not_search_vector_memory(tmp_path: Path) -> None:
    fake_store = FakeHistoricalStore()
    manager = MemoryManager(
        database_path=tmp_path / "memory.db",
        historical_store=fake_store,
    )

    prompt = PromptComposer.build_memory_block(
        server_id="server-1",
        memory_manager=manager,
        historical_query="What is the current disk usage?",
    )

    assert "RELEVANT HISTORICAL SERVER CONTEXT" not in prompt


def test_historical_memory_redacts_secrets() -> None:
    content = "password=secret-value\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"

    sanitized = HistoricalMemoryStore._sanitize(content)

    assert "secret-value" not in sanitized
    assert "BEGIN PRIVATE KEY" not in sanitized
