# This module defines the deployment context, which gathers all relevant information about a pending deployment request,including session details, user input, and the current state of the deployment process.It provides methods for saving and clearing pending deployment state within the session

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
    def pending_state(self) -> dict | None:
        return self.session_state.get(self.state_key)

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
