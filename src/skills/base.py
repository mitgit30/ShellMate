from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping
from typing import Any
from dataclasses import dataclass

from src.memory.memory_manager import MemoryManager


@dataclass
class SkillContext:
    session_id: str
    server_id: str
    user_message: str
    history: list[dict]
    session_state: dict


class BaseSkill(ABC):
    id: str
    name: str
    description: str

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._memory_manager = memory_manager

    def routing_summary(self) -> str:
        return f"{self.id}: {self.description}"

    def _memory_prompt_block(self, context: SkillContext) -> str:
        handoff = self._memory_manager.read_handoff(context.server_id)
        server_facts = self._memory_manager.read_server_facts(context.server_id)
        session = self._memory_manager.read_session(context.server_id)

        blocks: list[str] = []
        if handoff:
            blocks.append(f"--- HANDOFF FROM PREVIOUS SKILL ---\n{handoff}")
        if server_facts:
            blocks.append(f"--- KNOWN SERVER FACTS ---\n{server_facts}")
        if session:
            blocks.append(f"--- CURRENT SESSION CONTEXT ---\n{session}")
        return "\n\n".join(blocks)

    @abstractmethod
    def execute(self, context: SkillContext) -> Iterator[Mapping[str, Any]]:
        raise NotImplementedError
