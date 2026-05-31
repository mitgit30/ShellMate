from dataclasses import dataclass, field

from src.runtime.server_context import ServerContext


DEPLOYMENT_TYPE_DOCKER_SINGLE = "docker_single_app"
DEPLOYMENT_TYPE_DOCKER_COMPOSE = "docker_compose_app"


@dataclass
class DeploymentContext:
    session_id: str
    server_id: str
    user_message: str
    history: list[dict]
    server_context: ServerContext
    deployment_type: str
    project_path: str | None = None
    app_name: str | None = None
    exposed_port: int | None = None
    generated_files: dict[str, str] = field(default_factory=dict)

    @property
    def pending_state(self) -> dict:
        return self.server_context.pending_deployment

    @property
    def deployment_state(self) -> dict:
        return self.server_context.deployment

    def save_pending(self, stage: str, summary: str) -> None:
        self.server_context.set_pending_deployment(
            {
                "deployment_type": self.deployment_type,
                "project_path": self.project_path,
                "app_name": self.app_name,
                "exposed_port": self.exposed_port,
                "generated_files": self.generated_files,
                "stage": stage,
                "summary": summary,
            }
        )
        self.sync_to_server_context()

    def clear_pending(self) -> None:
        self.server_context.clear_pending_deployment()

    def sync_to_server_context(self) -> None:
        if self.project_path:
            self.server_context.remember_path(self.project_path, self.app_name)
        if self.app_name and not self.server_context.active_project_name:
            self.server_context.active_project_name = self.app_name
        if self.exposed_port:
            self.server_context.remember_port(self.exposed_port)
        self.deployment_state["deployment_type"] = self.deployment_type
