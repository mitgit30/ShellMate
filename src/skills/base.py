from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass


@dataclass
class SkillContext:
    session_id: str
    server_id: str
    user_message: str
    history: list[dict]


class BaseSkill(ABC):
    id: str
    name: str
    description: str

    def routing_summary(self) -> str:
        return f"{self.id}: {self.description}"

    @abstractmethod
    def execute(self, context: SkillContext) -> Iterator[dict]:
        raise NotImplementedError
