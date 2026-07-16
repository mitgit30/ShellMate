"""Deployment state models used by the deployment workflow."""

from dataclasses import dataclass, field


DEPLOYMENT_TYPE_DOCKER_SINGLE = "docker_single_app"
DEPLOYMENT_TYPE_DOCKER_COMPOSE = "docker_compose_app"


@dataclass
class DeploymentContext:
    session_id: str
    server_id: str
    user_message: str
    history: list[dict]
    session_state: dict
    deployment_type: str
    project_path: str | None = None
    app_name: str | None = None
    exposed_port: int | None = None
    generated_files: dict[str, str] = field(default_factory=dict)

    @property
    def state_key(self) -> str:
        return "pending_deployment"

    @property
    def metadata_key(self) -> str:
        return "deployment_context"

    @property
    def pending_state(self) -> dict | None:
        return self.session_state.get(self.state_key)

    @property
    def metadata_state(self) -> dict:
        return self.session_state.setdefault(self.metadata_key, {})

    def save_pending(self, stage: str, summary: str) -> None:
        self.session_state[self.state_key] = {
            "deployment_type": self.deployment_type,
            "project_path": self.project_path,
            "app_name": self.app_name,
            "exposed_port": self.exposed_port,
            "generated_files": self.generated_files,
            "stage": stage,
            "summary": summary,
        }

    def clear_pending(self) -> None:
        self.session_state.pop(self.state_key, None)

    def save_metadata(self) -> None:
        metadata = self.metadata_state
        metadata["deployment_type"] = self.deployment_type
        if self.project_path:
            metadata["project_path"] = self.project_path
        if self.app_name:
            metadata["app_name"] = self.app_name
        if self.exposed_port:
            metadata["exposed_port"] = self.exposed_port

    def clear_metadata(self) -> None:
        self.session_state.pop(self.metadata_key, None)
