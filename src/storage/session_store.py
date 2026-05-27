from dataclasses import dataclass, field


@dataclass
class RuntimeSession:
    session_id: str
    server_id: str
    messages: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, RuntimeSession] = {}

    def get_or_create(self, session_id: str, server_id: str) -> RuntimeSession:
        session = self._sessions.get(session_id)
        if session is None:
            session = RuntimeSession(session_id=session_id, server_id=server_id)
            self._sessions[session_id] = session
            return session

        session.server_id = server_id
        return session
