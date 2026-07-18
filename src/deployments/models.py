"""Deployment workflow state and context models."""

from dataclasses import asdict, dataclass, field
from typing import Any


DEPLOYMENT_TYPE_DOCKER_SINGLE = "docker_single_app"
DEPLOYMENT_TYPE_DOCKER_COMPOSE = "docker_compose_app"
DEPLOYMENT_STATE_KEY = "deployment_state"


@dataclass
class DeploymentState:
    """All persisted state required to continue a multi-turn deployment."""

    deployment_type: str | None = None
    project_path: str | None = None
    app_name: str | None = None
    exposed_port: int | None = None
    generated_files: dict[str, str] = field(default_factory=dict)
    stage: str | None = None
    summary: str | None = None
    root_path: str | None = None
    suggested_directories: list[str] = field(default_factory=list)
    awaiting_directory_selection: bool = False
    awaiting_directory_discovery_consent: bool = False

    @classmethod
    def from_session(cls, session_state: dict) -> "DeploymentState | None":
        current = session_state.get(DEPLOYMENT_STATE_KEY)
        if isinstance(current, cls):
            return current

        legacy_metadata = session_state.get("deployment_context", {})
        legacy_pending = session_state.get("pending_deployment", {})
        if not isinstance(legacy_metadata, dict):
            legacy_metadata = {}
        if not isinstance(legacy_pending, dict):
            legacy_pending = {}

        if not legacy_metadata and not legacy_pending:
            return None

        merged = {**legacy_metadata, **legacy_pending}
        state = cls(
            deployment_type=merged.get("deployment_type"),
            project_path=merged.get("project_path"),
            app_name=merged.get("app_name"),
            exposed_port=merged.get("exposed_port"),
            generated_files=dict(merged.get("generated_files", {})),
            stage=merged.get("stage"),
            summary=merged.get("summary"),
            root_path=legacy_metadata.get("root_path"),
            suggested_directories=list(legacy_metadata.get("suggested_directories", [])),
            awaiting_directory_selection=bool(
                legacy_metadata.get("awaiting_directory_selection", False)
            ),
            awaiting_directory_discovery_consent=bool(
                legacy_metadata.get("awaiting_directory_discovery_consent", False)
            ),
        )
        state.persist(session_state)
        session_state.pop("deployment_context", None)
        session_state.pop("pending_deployment", None)
        return state

    def persist(self, session_state: dict) -> None:
        session_state[DEPLOYMENT_STATE_KEY] = self

    def clear(self, session_state: dict) -> None:
        session_state.pop(DEPLOYMENT_STATE_KEY, None)
        session_state.pop("deployment_context", None)
        session_state.pop("pending_deployment", None)

    @property
    def has_pending_approval(self) -> bool:
        return self.stage == "awaiting_approval"

    @property
    def has_pending_work(self) -> bool:
        return any(
            (
                self.project_path,
                self.app_name,
                self.exposed_port,
                self.generated_files,
                self.stage,
                self.summary,
                self.root_path,
                self.suggested_directories,
                self.awaiting_directory_selection,
                self.awaiting_directory_discovery_consent,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __setitem__(self, key: str, value: Any) -> None:
        """Keep legacy mapping-style state updates compatible with the dataclass."""
        if not hasattr(self, key):
            raise KeyError(key)
        setattr(self, key, value)


@dataclass
class DeploymentContext:
    session_id: str
    server_id: str
    user_message: str
    history: list[dict]
    session_state: dict
    state: DeploymentState
    generated_files: dict[str, str] = field(default_factory=dict)

    @property
    def deployment_type(self) -> str:
        return self.state.deployment_type or DEPLOYMENT_TYPE_DOCKER_SINGLE

    @deployment_type.setter
    def deployment_type(self, value: str) -> None:
        self.state.deployment_type = value

    @property
    def project_path(self) -> str | None:
        return self.state.project_path

    @project_path.setter
    def project_path(self, value: str | None) -> None:
        self.state.project_path = value

    @property
    def app_name(self) -> str | None:
        return self.state.app_name

    @app_name.setter
    def app_name(self, value: str | None) -> None:
        self.state.app_name = value

    @property
    def exposed_port(self) -> int | None:
        return self.state.exposed_port

    @exposed_port.setter
    def exposed_port(self, value: int | None) -> None:
        self.state.exposed_port = value

    @property
    def generated_files(self) -> dict[str, str]:
        return self.state.generated_files

    @generated_files.setter
    def generated_files(self, value: dict[str, str]) -> None:
        self.state.generated_files = value

    def save_state(self, stage: str | None = None, summary: str | None = None) -> None:
        if stage is not None:
            self.state.stage = stage
        if summary is not None:
            self.state.summary = summary
        self.state.persist(self.session_state)

    def clear_state(self) -> None:
        self.state.clear(self.session_state)