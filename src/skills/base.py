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
        from src.runtime.prompt_composer import PromptComposer
        return PromptComposer.build_memory_block(context.server_id, self._memory_manager)


    @abstractmethod
    def execute(self, context: SkillContext) -> Iterator[Mapping[str, Any]]:
        raise NotImplementedError
