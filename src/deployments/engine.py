# This module defines the deployment engine class, which serves as the main entry point for handling deployment-related requests.

from collections.abc import Iterator

from src.deployments.docker_pipeline import DockerDeploymentPipeline
from src.deployments.models import (
    DEPLOYMENT_TYPE_DOCKER_COMPOSE,
    DEPLOYMENT_TYPE_DOCKER_SINGLE,
    DeploymentContext,
)
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import SkillContext
from src.tools.docker_tools import DockerTool


class DeploymentEngine:
    def __init__(self, model_client: OllamaModelClient, docker_tool: DockerTool) -> None:
        self._docker_pipeline = DockerDeploymentPipeline(
            model_client=model_client,
            docker_tool=docker_tool )

    def stream(self, context: SkillContext) -> Iterator[dict]: # will stream deployment steps and final result
        deployment_type = self._select_deployment_type(context)
        deployment_context = DeploymentContext(
            session_id=context.session_id,
            server_id=context.server_id,
            user_message=context.user_message,
            history=context.history,
            session_state=context.session_state,
            deployment_type=deployment_type, )
        yield from self._docker_pipeline.stream(deployment_context)

    @staticmethod
    def _select_deployment_type(context: SkillContext) -> str:
        
        lowered = context.user_message.lower()
        
        if any(keyword in lowered for keyword in ("compose", "mern", "lamp", "multi-container", "multi service")):
            return DEPLOYMENT_TYPE_DOCKER_COMPOSE

        pending = context.session_state.get("pending_deployment")
        if pending:
            
            return str(pending.get("deployment_type", DEPLOYMENT_TYPE_DOCKER_SINGLE))

        return DEPLOYMENT_TYPE_DOCKER_SINGLE
