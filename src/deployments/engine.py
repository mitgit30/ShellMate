import json
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
        self._model_client = model_client
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
            session_state=context.session_state,
            deployment_type=deployment_type,
        )
        self._hydrate_from_metadata(deployment_context)
        extracted = self._extract_preparation_details(deployment_context)
        self._apply_preparation_details(deployment_context, extracted)

        if self._should_inspect_directories(deployment_context, extracted):
            yield from self._inspect_directories(deployment_context)
            return

        selected_path = self._resolve_directory_selection(deployment_context, extracted)
        if selected_path:
            deployment_context.project_path = selected_path

        deployment_context.save_metadata()

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

    def _hydrate_from_metadata(self, context: DeploymentContext) -> None:
        metadata = context.metadata_state
        context.project_path = metadata.get("project_path")
        context.app_name = metadata.get("app_name")
        context.exposed_port = metadata.get("exposed_port")

    def _should_inspect_directories(self, context: DeploymentContext, extracted: dict) -> bool:
        metadata = context.metadata_state
        intent = str(extracted.get("prep_intent", "")).strip().lower()
        return intent == "inspect_directories" or (
            metadata.get("awaiting_directory_selection") and intent == "continue_directory_help"
        )

    def _inspect_directories(self, context: DeploymentContext) -> Iterator[dict]:
        root_path = self._extract_root_path(context.user_message) or context.metadata_state.get("root_path") or "~/shellmate-sites"
        context.metadata_state["root_path"] = root_path

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
                self._render_discovery_failure(context, root_path, tool_output)
            ):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        directories = self._parse_directories(tool_event.stdout)
        context.metadata_state["suggested_directories"] = directories
        context.metadata_state["awaiting_directory_selection"] = True
        context.save_metadata()

        yield {
            "type": "step_completed",
            "step": "deployment_discovery",
            "detail": "Directory inspection completed.",
        }

        message = self._render_discovery_result(context, root_path, directories)
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _resolve_directory_selection(self, context: DeploymentContext, extracted: dict) -> str | None:
        explicit_path = extracted.get("project_path")
        if isinstance(explicit_path, str) and explicit_path.strip():
            resolved = explicit_path.strip().rstrip(".,")
            context.metadata_state["awaiting_directory_selection"] = False
            context.metadata_state["project_path"] = resolved
            if extracted.get("app_name"):
                context.metadata_state["app_name"] = str(extracted["app_name"]).strip().lower().replace("_", "-")
            return resolved

        directories = context.metadata_state.get("suggested_directories", [])
        selected_name = str(extracted.get("selected_directory_name", "")).strip().lower()
        for directory in directories:
            basename = directory.rstrip("/").split("/")[-1].lower()
            if basename and selected_name and basename == selected_name:
                context.metadata_state["awaiting_directory_selection"] = False
                context.metadata_state["project_path"] = directory
                context.metadata_state["app_name"] = basename.replace("_", "-")
                return directory

        return None

    def _needs_preparation_prompt(self, context: DeploymentContext) -> bool:
        lowered = context.user_message.lower()
        no_known_path = not context.project_path
        return no_known_path and any(term in lowered for term in ("deploy", "deployment", "docker", "publish", "ship"))

    def _ask_preparation_question(self, context: DeploymentContext) -> Iterator[dict]:
        context.metadata_state["awaiting_directory_discovery_consent"] = True
        context.save_metadata()
        message = self._render_preparation_question(context)
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _needs_project_selection(self, context: DeploymentContext) -> bool:
        return bool(context.metadata_state.get("awaiting_directory_selection")) and not context.project_path

    def _prompt_for_project_selection(self, context: DeploymentContext) -> Iterator[dict]:
        directories = context.metadata_state.get("suggested_directories", [])
        message = self._render_project_selection_prompt(context, directories)
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _needs_port(self, context: DeploymentContext) -> bool:
        return context.project_path is not None and context.exposed_port is None

    def _prompt_for_port(self, context: DeploymentContext) -> Iterator[dict]:
        context.save_metadata()
        app_target = context.project_path or "that project"
        message = self._render_port_prompt(context, app_target)
        for token in self._chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _select_deployment_type(self, context: SkillContext) -> str:
        pending = context.session_state.get("pending_deployment")
        if pending:
            return str(pending.get("deployment_type", DEPLOYMENT_TYPE_DOCKER_SINGLE))

        metadata = context.session_state.get("deployment_context", {})
        remembered_type = metadata.get("deployment_type")
        if remembered_type:
            return str(remembered_type)

        payload = self._generate_json_from_skill_context(
            instruction=(
                "Choose the deployment type for this request. "
                "Return JSON only with key deployment_type. "
                "Valid values: docker_single_app, docker_compose_app. "
                "Use docker_compose_app for multi-service, compose, MERN, or LAMP style deployments. "
                "Otherwise use docker_single_app."
            ),
            context=context,
        )
        deployment_type = str(payload.get("deployment_type", DEPLOYMENT_TYPE_DOCKER_SINGLE)).strip()
        if deployment_type in {DEPLOYMENT_TYPE_DOCKER_COMPOSE, DEPLOYMENT_TYPE_DOCKER_SINGLE}:
            return deployment_type
        return DEPLOYMENT_TYPE_DOCKER_SINGLE

    def _extract_preparation_details(self, context: DeploymentContext) -> dict:
        payload = self._generate_json(
            instruction=(
                "Extract deployment preparation details from the full conversation context. "
                "Return JSON only with keys: prep_intent, project_path, app_name, exposed_port, root_path, selected_directory_name. "
                "Valid prep_intent values: inspect_directories, continue_directory_help, provide_details, ask_for_preparation, continue. "
                "Use null for unknown values. "
                "Prefer conversation history and existing deployment metadata when they clearly refer to the same task."
            ),
            context=context,
            extra={
                "deployment_metadata": context.metadata_state,
                "pending_deployment": context.pending_state or {},
            },
        )
        normalized: dict[str, object] = {}
        for key in ("prep_intent", "project_path", "app_name", "root_path", "selected_directory_name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip().rstrip(".,")
        exposed_port = payload.get("exposed_port")
        if isinstance(exposed_port, int):
            normalized["exposed_port"] = exposed_port
        elif isinstance(exposed_port, str) and exposed_port.isdigit():
            normalized["exposed_port"] = int(exposed_port)
        return normalized

    @staticmethod
    def _apply_preparation_details(context: DeploymentContext, extracted: dict) -> None:
        if extracted.get("project_path"):
            context.project_path = str(extracted["project_path"])
        if extracted.get("app_name"):
            context.app_name = str(extracted["app_name"]).lower().replace(" ", "-")
        if extracted.get("exposed_port") is not None:
            context.exposed_port = int(extracted["exposed_port"])
        if extracted.get("root_path"):
            context.metadata_state["root_path"] = str(extracted["root_path"])

    def _render_discovery_failure(self, context: DeploymentContext, root_path: str, tool_output: str) -> str:
        return self._generate_text(
            instruction=(
                "The directory discovery step failed. "
                "Explain that you could not inspect the requested server location, "
                "mention the root path briefly, and suggest giving the exact project path directly."
            ),
            context=context,
            extra={"root_path": root_path, "tool_output": tool_output},
            fallback=(
                "I couldn't inspect that server location yet.\n\n"
                "If you want, send me the exact project path directly and I can continue from there.\n\n"
                f"Technical details:\n{tool_output}"
            ),
        )

    def _render_discovery_result(self, context: DeploymentContext, root_path: str, directories: list[str]) -> str:
        return self._generate_text(
            instruction=(
                "Summarize the result of directory discovery for deployment preparation. "
                "If directories were found, present them clearly and ask the user which one to deploy. "
                "If none were found, say so and ask for the exact path."
            ),
            context=context,
            extra={"root_path": root_path, "directories": directories[:8]},
            fallback=(
                f"I checked `{root_path}` and found these likely project directories:\n\n"
                + "\n".join(f"- `{directory}`" for directory in directories[:8])
                + "\n\nSend me the directory you want to deploy, and include the public port if you already know it."
                if directories
                else f"I checked `{root_path}`, but I didn't find any immediate subdirectories to deploy from.\n\nIf you already know the project path, send it directly and I’ll continue."
            ),
        )

    def _render_preparation_question(self, context: DeploymentContext) -> str:
        return self._generate_text(
            instruction=(
                "Ask the user whether you should inspect the server for likely project directories first, "
                "or whether they want to provide the exact project path directly."
            ),
            context=context,
            extra={"deployment_metadata": context.metadata_state},
            fallback=(
                "I can help with that. Before I prepare the deployment, should I inspect the server and look for likely project directories first?\n\n"
                "If yes, tell me something like `check ~/shellmate-sites` or `inspect the home directory`.\n"
                "If you already know the exact project path, send it directly along with the public port."
            ),
        )

    def _render_project_selection_prompt(self, context: DeploymentContext, directories: list[str]) -> str:
        return self._generate_text(
            instruction=(
                "Ask the user to choose which directory should be deployed. "
                "Use the discovered directories when available and keep the prompt natural."
            ),
            context=context,
            extra={"directories": directories[:8]},
            fallback=(
                "I still need the project directory before I can prepare the deployment.\n\n"
                "Send the full path and, if you know it, the public port you want to expose."
            ),
        )

    def _render_port_prompt(self, context: DeploymentContext, app_target: str) -> str:
        return self._generate_text(
            instruction=(
                "Ask the user for the public port to expose for the deployment. "
                "Mention that you already have the project path."
            ),
            context=context,
            extra={"app_target": app_target},
            fallback=(
                f"I’ve got the project path for `{app_target}`.\n\n"
                "Now send me the public port you want to expose, for example `port 3000`."
            ),
        )

    def _generate_json(self, instruction: str, context: DeploymentContext, extra: dict | None = None) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's deployment preparation assistant.\n"
                    f"{instruction}\n"
                    "Return valid JSON only."
                ),
            },
            *context.history[-8:],
            {"role": "user", "content": context.user_message},
        ]
        if extra:
            messages.append({"role": "system", "content": self._safe_json(extra)})
        response = self._model_client.chat(messages=messages, tools=[])
        content = response.get("message", {}).get("content", "") or "{}"
        try:
            payload = __import__("json").loads(content)
            return payload if isinstance(payload, dict) else {}
        except (__import__("json").JSONDecodeError, TypeError, ValueError):
            return {}

    def _generate_json_from_skill_context(self, instruction: str, context: SkillContext) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's deployment preparation assistant.\n"
                    f"{instruction}\n"
                    "Return valid JSON only."
                ),
            },
            *context.history[-8:],
            {"role": "user", "content": context.user_message},
            {
                "role": "system",
                "content": json.dumps(
                    {
                        "session_state": context.session_state,
                    },
                    ensure_ascii=True,
                ),
            },
        ]
        response = self._model_client.chat(messages=messages, tools=[])
        content = response.get("message", {}).get("content", "") or "{}"
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _generate_text(self, instruction: str, context: DeploymentContext, fallback: str, extra: dict | None = None) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's deployment preparation assistant.\n"
                    f"{instruction}\n"
                    "Respond naturally, clearly, and briefly. Do not mention internal pipeline mechanics."
                ),
            },
            *context.history[-6:],
            {"role": "user", "content": context.user_message},
            {
                "role": "system",
                "content": self._safe_json(
                    {
                        "deployment_type": context.deployment_type,
                        "project_path": context.project_path,
                        "app_name": context.app_name,
                        "exposed_port": context.exposed_port,
                        "metadata": context.metadata_state,
                        **(extra or {}),
                    }
                ),
            },
        ]
        response = self._model_client.chat(messages=messages, tools=[])
        content = (response.get("message", {}).get("content", "") or "").strip()
        return content or fallback

    @staticmethod
    def _safe_json(payload: dict) -> str:
        import json

        return json.dumps(payload, ensure_ascii=True)

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
