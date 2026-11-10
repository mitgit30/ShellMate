from types import SimpleNamespace

import pytest

from src.runtime.openrouter_client import OpenRouterModelClient


class FakeCompletions:
    def __init__(self, response: SimpleNamespace) -> None:
        self.response = response
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.response


def test_chat_normalizes_openrouter_tool_calls_to_runtime_shape() -> None:
    message = SimpleNamespace(
        content=None,
        tool_calls=[
            SimpleNamespace(
                id="call_123",
                type="function",
                function=SimpleNamespace(
                    name="run_ssh_command",
                    arguments='{"command":"df -h"}',
                ),
            )
        ],
    )
    completions = FakeCompletions(
        SimpleNamespace(choices=[SimpleNamespace(message=message)])
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    client = OpenRouterModelClient(client=fake_client, model="test/model:free")
    messages = [{"role": "user", "content": "Check disk usage"}]
    tools = [{"type": "function", "function": {"name": "run_ssh_command"}}]

    response = client.chat(messages=messages, tools=tools)

    assert response == {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "run_ssh_command",
                        "arguments": '{"command":"df -h"}',
                    },
                }
            ],
        }
    }
    assert completions.calls == [
        {"model": "test/model:free", "messages": messages, "tools": tools}
    ]


def test_chat_raises_when_openrouter_returns_no_choices() -> None:
    completions = FakeCompletions(SimpleNamespace(choices=[]))
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions)
    )
    client = OpenRouterModelClient(client=fake_client, model="test/model:free")

    with pytest.raises(RuntimeError, match="empty chat completion"):
        client.chat(messages=[{"role": "user", "content": "Hi"}], tools=[])


def test_client_requires_openrouter_api_key_when_no_client_is_injected(monkeypatch) -> None:
    import src.runtime.openrouter_client as openrouter_module

    monkeypatch.setattr(
        openrouter_module,
        "get_runtime_settings",
        lambda: SimpleNamespace(
            openrouter_model="test/model:free",
            openrouter_api_key=None,
            openrouter_base_url="https://openrouter.ai/api/v1",
        ),
    )

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterModelClient()
