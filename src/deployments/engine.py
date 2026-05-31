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
from src.tools.ssh_tool import SSHCommandTool


class DeploymentEngine:
    def __init__(
        self,
        model_client: OllamaModelClient,
        docker_tool: DockerTool,
        ssh_tool: SSHCommandTool,
    ) -> None:
        self._docker_pipeline = DockerDeploymentPipeline(
            model_client=model_client,
            docker_tool=docker_tool,
        )
        self._ssh_tool = ssh_tool

    def stream(self, context: SkillContext) -> Iterator[dict]:
        deployment_type = self._select_deployment_type(context)
        deployment_context = DeploymentContext(
            session_id=context.session_id,
            server_id=context.server_id,
            user_message=context.user_message,
            history=context.history,
            server_context=context.server_context,
            deployment_type=deployment_type,
        )
        self._hydrate_from_server_context(deployment_context)

        if self._should_inspect_directories(deployment_context):
            yield from self._inspect_directories(deployment_context)
            return

        selected_path = self._resolve_directory_selection(deployment_context)
        if selected_path:
            deployment_context.project_path = selected_path

        parsed_port = self._extract_port(deployment_context.user_message)
        if parsed_port is not None:
            deployment_context.exposed_port = parsed_port

        deployment_context.sync_to_server_context()

        if self._needs_preparation_prompt(deployment_context):
            yield from self._ask_preparation_question(deployment_context)
            return

        if self._needs_project_selection(deployment_context):
            yield from self._prompt_for_project_selection(deployment_context)
            return

        if self._needs_port(deployment_context):
            yield from self._prompt_for_port(deployment_context)
            return

        yield from self._docker_pipeline.stream(deployment_context)

    def _hydrate_from_server_context(self, context: DeploymentContext) -> None:
        context.project_path = context.server_context.active_project_path
        context.app_name = context.server_context.active_project_name
        context.exposed_port = context.server_context.active_port

    def _should_inspect_directories(self, context: DeploymentContext) -> bool:
        lowered = context.user_message.lower()
        has_check_language = any(
            term in lowered for term in ("check it", "look for", "inspect", "show directories", "find directories")
        )
        has_target_hint = any(term in lowered for term in ("shellmate-sites", "directory", "folder", "project"))
        return has_check_language and has_target_hint or context.deployment_state.get("awaiting_directory_selection") and has_check_language

    def _inspect_directories(self, context: DeploymentContext) -> Iterator[dict]:
        root_path = self._extract_root_path(context.user_message) or context.deployment_state.get("root_path") or "~/shellmate-sites"
        context.deployment_state["root_path"] = root_path

        yield {
            "type": "step_started",
            "step": "deployment_discovery",
            "detail": "Inspecting likely project directories on the server.",
        }
        tool_event, tool_output = self._ssh_tool.execute(
            server_id=context.server_id,
            arguments={
                "command": self._directory_discovery_command(root_path),
                "reason": "List likely project directories before deployment.",
            },
        )
        yield {
            "type": "tool_called",
            "tool_name": tool_event.tool_name,
            "command": tool_event.command,
        }
        yield {
            "type": "tool_event",
            "tool_name": tool_event.tool_name,
            "command": tool_event.command,
            "exit_status": tool_event.exit_status,
            "stdout": tool_event.stdout,
            "stderr": tool_event.stderr,
        }
        if tool_event.exit_status != 0:
            yield {
                "type": "step_completed",
                "step": "deployment_discovery",
                "detail": "Directory inspection failed.",
            }
            for token in self._chunk_text(
                "I couldn't inspect that server location yet.\n\n"
                "If you want, send me the exact project path directly and I can continue from there.\n\n"
                f"Technical details:\n{tool_output}"
            ):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        directories = self._parse_directories(tool_event.stdout)
        context.server_context.candidate_paths = directories
        context.deployment_state["awaiting_directory_selection"] = True
        context.sync_to_server_context()

        yield {
            "type": "step_completed",
            "step": "deployment_discovery",
            "detail": "Directory inspection completed.",
        }

        if not directories:
            message = (
                f"I checked `{root_path}`, but I didn't find any immediate subdirectories to deploy from.\n\n"
                "If you already know the project path, send it directly and I’ll continue."
            )
        else:
            lines = "\n".join(f"- `{directory}`" for directory in directories[:8])
            message = (
                f"I checked `{root_path}` and found these likely project directories:\n\n"
                f"{lines}\n\n"
                "Send me the directory you want to deploy, and include the public port if you already know it."
            )
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _resolve_directory_selection(self, context: DeploymentContext) -> str | None:
        explicit_path = self._extract_explicit_path(context.user_message)
        if explicit_path:
            context.deployment_state["awaiting_directory_selection"] = False
            context.server_context.remember_path(explicit_path)
            return explicit_path

        directories = context.server_context.candidate_paths
        lowered = context.user_message.lower()
        for directory in directories:
            basename = directory.rstrip("/").split("/")[-1].lower()
            if basename and basename in lowered:
                context.deployment_state["awaiting_directory_selection"] = False
                context.server_context.remember_path(directory, basename.replace("_", "-"))
                return directory

        return None

    def _needs_preparation_prompt(self, context: DeploymentContext) -> bool:
        lowered = context.user_message.lower()
        no_known_path = not context.project_path
        return no_known_path and any(term in lowered for term in ("deploy", "deployment", "docker", "publish", "ship"))

    def _ask_preparation_question(self, context: DeploymentContext) -> Iterator[dict]:
        context.deployment_state["awaiting_directory_discovery_consent"] = True
        context.sync_to_server_context()
        message = (
            "I can help with that. Before I prepare the deployment, should I inspect the server and look for likely project directories first?\n\n"
            "If yes, tell me something like `check ~/shellmate-sites` or `inspect the home directory`.\n"
            "If you already know the exact project path, send it directly along with the public port."
        )
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _needs_project_selection(self, context: DeploymentContext) -> bool:
        return bool(context.deployment_state.get("awaiting_directory_selection")) and not context.project_path

    def _prompt_for_project_selection(self, context: DeploymentContext) -> Iterator[dict]:
        directories = context.server_context.candidate_paths
        if directories:
            lines = "\n".join(f"- `{directory}`" for directory in directories[:8])
            message = (
                "I still need you to choose which directory to deploy.\n\n"
                f"{lines}\n\n"
                "Send the directory name or the full path, and include the public port if you know it."
            )
        else:
            message = (
                "I still need the project directory before I can prepare the deployment.\n\n"
                "Send the full path and, if you know it, the public port you want to expose."
            )
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _needs_port(self, context: DeploymentContext) -> bool:
        return context.project_path is not None and context.exposed_port is None

    def _prompt_for_port(self, context: DeploymentContext) -> Iterator[dict]:
        context.sync_to_server_context()
        app_target = context.project_path or "that project"
        message = (
            f"I’ve got the project path for `{app_target}`.\n\n"
            "Now send me the public port you want to expose, for example `port 3000`."
        )
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    @staticmethod
    def _select_deployment_type(context: SkillContext) -> str:
        lowered = context.user_message.lower()
        if any(keyword in lowered for keyword in ("compose", "mern", "lamp", "multi-container", "multi service")):
            return DEPLOYMENT_TYPE_DOCKER_COMPOSE

        pending = context.server_context.pending_deployment
        if pending:
            return str(pending.get("deployment_type", DEPLOYMENT_TYPE_DOCKER_SINGLE))

        deployment_state = context.server_context.deployment
        if deployment_state.get("deployment_type"):
            return str(deployment_state["deployment_type"])

        return DEPLOYMENT_TYPE_DOCKER_SINGLE

    @staticmethod
    def _extract_port(message: str) -> int | None:
        import re

        match = re.search(r"\bport\b\s*[:=\-]?\s*(\d{2,5})\b", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        fallback = re.search(r"\b(\d{2,5})\b", message)
        if fallback:
            value = int(fallback.group(1))
            if 1 <= value <= 65535:
                return value
        return None

    @staticmethod
    def _extract_root_path(message: str) -> str | None:
        import re

        match = re.search(r"(?:check|inspect|look\s+for)\s+([~/.\w\-/]+)", message, re.IGNORECASE)
        if match:
            return match.group(1).strip().rstrip(".,")
        return None

    @staticmethod
    def _extract_explicit_path(message: str) -> str | None:
        import re

        match = re.search(
            r"(?:path|directory|folder|project)\s+(?:is\s+|at\s+)?([~/.\w\-/]+)",
            message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().rstrip(".,")
        if "/" in message or "~/" in message:
            path_like = re.search(r"([~/][\w.\-/]+)", message)
            if path_like:
                return path_like.group(1).strip().rstrip(".,")
        return None

    @staticmethod
    def _directory_discovery_command(root_path: str) -> str:
        if root_path == "~":
            resolved = "$HOME"
        elif root_path.startswith("~/"):
            resolved = f'$HOME/{root_path[2:]}'
        else:
            resolved = root_path
        return (
            f'ROOT_PATH="{resolved}"\n'
            'if [ ! -d "$ROOT_PATH" ]; then\n'
            '  echo "__SHELLMATE_MISSING_ROOT__:$ROOT_PATH"\n'
            "  exit 1\n"
            "fi\n"
            'find "$ROOT_PATH" -mindepth 1 -maxdepth 1 -type d | sort\n'
        )

    @staticmethod
    def _parse_directories(stdout: str) -> list[str]:
        directories: list[str] = []
        for line in stdout.splitlines():
            cleaned = line.strip()
            if cleaned and not cleaned.startswith("__SHELLMATE_MISSING_ROOT__:"):
                directories.append(cleaned)
        return directories

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix
