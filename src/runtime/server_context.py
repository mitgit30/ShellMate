import json
import re
from dataclasses import asdict, dataclass, field

from src.runtime.ollama_client import OllamaModelClient


@dataclass
class ServerContext:
    paths_found: dict[str, str] = field(default_factory=dict)
    packages_found: dict[str, str] = field(default_factory=dict)
    ports_mentioned: list[int] = field(default_factory=list)
    containers_mentioned: list[str] = field(default_factory=list)
    candidate_paths: list[str] = field(default_factory=list)
    active_project_path: str | None = None
    active_project_name: str | None = None
    active_port: int | None = None
    latest_builder_output: dict = field(default_factory=dict)
    pending_deployment: dict = field(default_factory=dict)
    deployment: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, payload: str | None) -> "ServerContext":
        if not payload:
            return cls()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            paths_found=dict(data.get("paths_found", {})),
            packages_found=dict(data.get("packages_found", {})),
            ports_mentioned=[int(port) for port in data.get("ports_mentioned", []) if str(port).isdigit()],
            containers_mentioned=[str(name) for name in data.get("containers_mentioned", [])],
            candidate_paths=[str(path) for path in data.get("candidate_paths", [])],
            active_project_path=data.get("active_project_path"),
            active_project_name=data.get("active_project_name"),
            active_port=data.get("active_port"),
            latest_builder_output=dict(data.get("latest_builder_output", {})),
            pending_deployment=dict(data.get("pending_deployment", {})),
            deployment=dict(data.get("deployment", {})),
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    def prompt_summary(self) -> str:
        lines: list[str] = []
        if self.active_project_path:
            lines.append(f"Active project path: {self.active_project_path}")
        if self.active_project_name:
            lines.append(f"Active project name: {self.active_project_name}")
        if self.active_port:
            lines.append(f"Active public port: {self.active_port}")
        if self.candidate_paths:
            lines.append("Candidate paths: " + ", ".join(self.candidate_paths[:6]))
        if self.containers_mentioned:
            lines.append("Known containers: " + ", ".join(self.containers_mentioned[:6]))
        if self.packages_found:
            package_names = ", ".join(f"{name}={version}" for name, version in list(self.packages_found.items())[:6])
            lines.append(f"Known packages: {package_names}")
        return "\n".join(lines) if lines else "No structured server facts discovered yet."

    def remember_path(self, path: str, name: str | None = None) -> None:
        cleaned = path.strip()
        if not cleaned:
            return
        key = name or cleaned.rstrip("/").split("/")[-1]
        self.paths_found[key] = cleaned
        self.active_project_path = cleaned
        self.active_project_name = name or key
        if cleaned not in self.candidate_paths:
            self.candidate_paths.append(cleaned)

    def remember_port(self, port: int | None) -> None:
        if port is None:
            return
        if port not in self.ports_mentioned:
            self.ports_mentioned.append(port)
        self.active_port = port

    def remember_builder_output(self, payload: dict) -> None:
        self.latest_builder_output = dict(payload)
        project_path = payload.get("project_path")
        if isinstance(project_path, str) and project_path.strip():
            slug = payload.get("site_slug")
            self.remember_path(project_path, str(slug).strip() if slug else None)

    def set_pending_deployment(self, payload: dict) -> None:
        self.pending_deployment = dict(payload)
        self.deployment["last_mode"] = payload.get("deployment_type")

    def clear_pending_deployment(self) -> None:
        self.pending_deployment = {}


class ContextExtractor:
    def __init__(self, model_client: OllamaModelClient) -> None:
        self._model_client = model_client

    def extract(
        self,
        assistant_message: str,
        server_context: ServerContext,
        user_message: str = "",
        tool_outputs: list[str] | None = None,
    ) -> ServerContext:
        updated = ServerContext.from_json(server_context.to_json())
        self._apply_regex_facts(updated, "\n".join(filter(None, [user_message, assistant_message, *(tool_outputs or [])])))
        llm_facts = self._extract_with_llm(
            assistant_message=assistant_message,
            user_message=user_message,
            server_context=updated,
            tool_outputs=tool_outputs or [],
        )
        self._merge_facts(updated, llm_facts)
        return updated

    def _extract_with_llm(
        self,
        assistant_message: str,
        user_message: str,
        server_context: ServerContext,
        tool_outputs: list[str],
    ) -> dict:
        prompt = (
            "Extract structured server and project facts from the conversation and tool results.\n"
            "Return JSON only with these keys:\n"
            "{\n"
            '  "paths_found": {"name": "full_path"},\n'
            '  "packages_found": {"name": "version"},\n'
            '  "ports_mentioned": [],\n'
            '  "containers_mentioned": [],\n'
            '  "candidate_paths": [],\n'
            '  "active_project_path": null,\n'
            '  "active_project_name": null,\n'
            '  "active_port": null\n'
            "}\n"
            "Only include facts that are explicitly stated or strongly implied.\n"
            "If nothing is present for a field, return an empty object, empty array, or null.\n"
        )
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": (
                    f"Existing context JSON:\n{server_context.to_json()}\n\n"
                    f"User message:\n{user_message}\n\n"
                    f"Assistant message:\n{assistant_message}\n\n"
                    f"Tool outputs:\n{chr(10).join(tool_outputs)}"
                ),
            },
        ]
        try:
            response = self._model_client.chat(messages=messages, tools=[])
            content = response.get("message", {}).get("content", "") or "{}"
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _merge_facts(self, server_context: ServerContext, facts: dict) -> None:
        for name, path in dict(facts.get("paths_found", {})).items():
            if isinstance(path, str) and path.strip():
                server_context.remember_path(path, str(name))
        for name, version in dict(facts.get("packages_found", {})).items():
            server_context.packages_found[str(name)] = str(version)
        for path in facts.get("candidate_paths", []) or []:
            if isinstance(path, str) and path.strip() and path not in server_context.candidate_paths:
                server_context.candidate_paths.append(path)
        for name in facts.get("containers_mentioned", []) or []:
            cleaned = str(name).strip()
            if cleaned and cleaned not in server_context.containers_mentioned:
                server_context.containers_mentioned.append(cleaned)
        for port in facts.get("ports_mentioned", []) or []:
            if str(port).isdigit():
                server_context.remember_port(int(port))
        active_project_path = facts.get("active_project_path")
        active_project_name = facts.get("active_project_name")
        active_port = facts.get("active_port")
        if isinstance(active_project_path, str) and active_project_path.strip():
            server_context.remember_path(active_project_path, str(active_project_name).strip() if active_project_name else None)
        if isinstance(active_port, int):
            server_context.remember_port(active_port)

    def _apply_regex_facts(self, server_context: ServerContext, text: str) -> None:
        for match in re.findall(r"([~/][\w.\-/]+|/[\w.\-/]+)", text):
            cleaned = match.strip().rstrip(".,")
            if cleaned and len(cleaned) > 1:
                server_context.remember_path(cleaned)

        for match in re.findall(r"\bport\b\s*[:=\-]?\s*(\d{2,5})\b", text, re.IGNORECASE):
            value = int(match)
            if 1 <= value <= 65535:
                server_context.remember_port(value)

        if server_context.active_project_path and not server_context.active_project_name:
            server_context.active_project_name = server_context.active_project_path.rstrip("/").split("/")[-1]
