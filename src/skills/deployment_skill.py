from collections.abc import Iterator

from src.deployments.engine import DeploymentEngine
from src.skills.base import BaseSkill, SkillContext


class DeploymentSkill(BaseSkill):
    id = "deployment"
    name = "Deployment Engine"
    description = (
        "Handles Docker deployment requests with a structured, approval-based pipeline "
        "instead of free-form conversational execution."
    )

    def __init__(self, deployment_engine: DeploymentEngine) -> None:
        self._deployment_engine = deployment_engine

    def execute(self, context: SkillContext) -> Iterator[dict]:
        yield {
            "type": "step_started",
            "step": "deployment_mode",
            "detail": "Switched from conversational mode to structured deployment mode.",
        }
        yield from self._deployment_engine.stream(context)
