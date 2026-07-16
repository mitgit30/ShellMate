import json
from collections.abc import Iterator

from src.deployments.models import (
    DEPLOYMENT_TYPE_DOCKER_COMPOSE,
    DEPLOYMENT_TYPE_DOCKER_SINGLE,
    DeploymentContext,
)
from src.runtime.ollama_client import OllamaModelClient
from src.tools.docker_tools import DockerTool


class DockerDeploymentPipeline:
    def __init__(self, model_client: OllamaModelClient, docker_tool: DockerTool) -> None:
        self._model_client = model_client
        self._docker_tool = docker_tool

    def stream(self, context: DeploymentContext) -> Iterator[dict]:
        turn_intent = self._detect_turn_intent(context)

        if turn_intent == "cancel":
            context.clear_pending()
            for token in self._chunk_text(self._render_cancel_message(context)):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        if turn_intent == "approve":
            yield from self._resume_after_approval(context)
            return

        pending = context.pending_state or {}
        extracted = self._extract_request_details(context, pending)
        if extracted.get("project_path"):
            context.project_path = str(extracted["project_path"]).strip()
        if extracted.get("exposed_port") is not None:
            context.exposed_port = int(extracted["exposed_port"])
        if extracted.get("app_name"):
            context.app_name = str(extracted["app_name"]).strip()

        if context.project_path is None:
            context.project_path = pending.get("project_path")
        if context.exposed_port is None:
            context.exposed_port = pending.get("exposed_port")
        if not context.app_name and pending.get("app_name"):
            context.app_name = pending.get("app_name")
        if not context.app_name:
            context.app_name = self._derive_app_name(context.project_path)

        yield {
            "type": "step_started",
            "step": "deployment_validate",
            "detail": "Running deployment validation checks.",
        }

        validation_errors = self._run_validation(context)

        if validation_errors:
            yield {
                "type": "step_completed",
                "step": "deployment_validate",
                "detail": "Deployment validation blocked.",
            }

            for token in self._chunk_text(self._render_validation_message(context, validation_errors)):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        yield {
            "type": "step_completed",
            "step": "deployment_validate",
            "detail": "Validation checks passed.",
        }

        missing_inputs: list[str] = []
        if not context.project_path:
            
            missing_inputs.append("project path")
        if not context.exposed_port:
            missing_inputs.append("port to expose")

        if missing_inputs:
            question = self._render_missing_inputs_message(context, missing_inputs)
            for token in self._chunk_text(question):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        yield {
            "type": "step_started",
            "step": "deployment_generate",
            "detail": "Generating deployment files and plan.",
        }
        generated_files = self._generate_files(context)
        context.generated_files = generated_files
        summary = self._render_approval_summary(context)

        context.save_pending(stage="awaiting_approval", summary=summary)
        yield {
            "type": "step_completed",
            "step": "deployment_generate",
            "detail": "Deployment files generated and approval requested.",
        }
        for token in self._chunk_text(summary):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _resume_after_approval(self, context: DeploymentContext) -> Iterator[dict]:
        pending = context.pending_state
        if not pending:
            for token in self._chunk_text(self._render_no_pending_approval_message(context)):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        context.deployment_type = str(pending["deployment_type"])
        context.project_path = pending.get("project_path")
        context.app_name = pending.get("app_name")
        context.exposed_port = pending.get("exposed_port")
        context.generated_files = dict(pending.get("generated_files", {}))

        yield {
            "type": "step_started",
            "step": "deployment_execute",
            "detail": "Approval received. Executing deployment pipeline.",
        }

        for filename, content in context.generated_files.items():
            tool_event, tool_output = self._docker_tool.execute(
                server_id=context.server_id,
                arguments={
                    "action": "write_file",
                    "target_path": f"{context.project_path}/{filename}",
                    "content": content,
                },)
            yield self._tool_called_event("write_file", tool_event.command)
            yield self._tool_event(tool_event)
            if tool_event.exit_status != 0:
                yield {
                    "type": "step_completed",
                    "step": "deployment_execute",
                    "detail": "Deployment file upload failed.",
                }
                for token in self._chunk_text(self._render_execution_failure(
                    context,
                    "I wasn't able to prepare the deployment files on the server.",
                    tool_output,
                )):
                    yield {"type": "token", "content": token}
                yield {"type": "done"}
                return

        execution_actions = self._execution_actions(context)
        for action, arguments in execution_actions:
            tool_event, tool_output = self._docker_tool.execute(
                server_id=context.server_id,
                arguments=arguments,
            )
            yield self._tool_called_event(action, tool_event.command)
            yield self._tool_event(tool_event)
            if tool_event.exit_status != 0:
                yield {
                    "type": "step_completed",
                    "step": "deployment_execute",
                    "detail": "Deployment execution failed.",
                }
                for token in self._chunk_text(self._render_execution_failure(
                    context,
                    "The deployment started, but one of the Docker steps failed.",
                    tool_output,
                )):
                    yield {"type": "token", "content": token}
                yield {"type": "done"}
                return

        yield {
            "type": "step_completed",
            "step": "deployment_execute",
            "detail": "Deployment commands completed.",
        }

        yield {
            "type": "step_started",
            "step": "deployment_verify",
            "detail": "Verifying deployment health and status.",
        }
        verification_output = self._run_verification(context)
        context.clear_pending()
        yield {
            "type": "step_completed",
            "step": "deployment_verify",
            "detail": "Verification completed.",
        }
        for token in self._chunk_text(verification_output):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _run_validation(self, context: DeploymentContext) -> list[dict[str, str]]:
        checks: list[tuple[str, dict]] = [
            ("docker", {"action": "check_docker"}),
            ("project_path", {"action": "check_directory", "target_path": context.project_path}),
        ]

        if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            checks.append(("compose", {"action": "check_compose"}))

        if context.exposed_port:
            checks.append(("port", {"action": "check_port_free", "port": context.exposed_port}))

        errors: list[dict[str, str]] = []
        for check_name, arguments in checks:
            if check_name == "project_path" and arguments.get("target_path") is None:
                continue
            tool_event, tool_output = self._docker_tool.execute(server_id=context.server_id, arguments=arguments)

            if tool_event.exit_status != 0:
                if check_name == "docker":
                    errors.append({"check": "docker", "message": "Docker is not installed or not reachable on the server.", "details": tool_output})
                elif check_name == "compose":
                    errors.append({"check": "compose", "message": "Docker Compose is not available on the server.", "details": tool_output})
                elif check_name == "project_path":
                    errors.append({"check": "project_path", "message": f"Project directory '{context.project_path}' was not found.", "details": tool_output})
                elif check_name == "port":
                    errors.append({"check": "port", "message": f"Port {context.exposed_port} is already in use.", "details": tool_output})

        return errors

    def _generate_files(self, context: DeploymentContext) -> dict[str, str]:
        if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            return self._generate_compose_files(context)
        return self._generate_single_app_files(context)

    def _generate_compose_files(self, context: DeploymentContext) -> dict[str, str]:
        prompt = (
            "You generate Docker deployment files for Linux servers.\n"
            "Return JSON only with keys docker_compose_yml and dockerfile.\n"
            "Use the user's request and detected metadata.\n"
            "Expose the application on the provided port.\n"
            "Keep the output production-safe and minimal.\n"
            f"Project path: {context.project_path}\n"
            f"App name: {context.app_name}\n"
            f"Port: {context.exposed_port}\n"
            f"User request: {context.user_message}\n"
        )
        response = self._model_client.chat(
            messages=[{"role": "system", "content": prompt}],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        try:
            payload = json.loads(content)
            compose_text = str(payload["docker_compose_yml"])
            dockerfile_text = str(payload["dockerfile"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            compose_text = self._fallback_compose(context)
            dockerfile_text = self._fallback_dockerfile()

        return {
            "docker-compose.yml": compose_text,
            "Dockerfile": dockerfile_text,
        }
        

    def _generate_single_app_files(self, context: DeploymentContext) -> dict[str, str]:
        if self._is_static_site_project(context):
            return self._generate_static_site_files(context)

        prompt = (
            "You generate a Dockerfile for deploying a single Linux-hosted app.\n"
            "Return JSON only with key dockerfile.\n"
            "Use a concise production-safe default.\n"
            f"App name: {context.app_name}\n"
            f"Port: {context.exposed_port}\n"
            f"User request: {context.user_message}\n"
        )
        response = self._model_client.chat(
            messages=[{"role": "system", "content": prompt}],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        try:
            payload = json.loads(content)
            dockerfile_text = str(payload["dockerfile"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            dockerfile_text = self._fallback_dockerfile()

        return {"Dockerfile": dockerfile_text}

    def _generate_static_site_files(self, context: DeploymentContext) -> dict[str, str]:
        prompt = (
            "You generate Docker deployment files for a static website.\n"
            "The project already contains HTML, CSS, and JavaScript files.\n"
            "Return JSON only with keys dockerfile and nginx_conf.\n"
            "Use nginx as the runtime.\n"
            "Serve the site from /usr/share/nginx/html.\n"
            "Configure nginx to listen on port 80 and serve index.html for root requests.\n"
            "Keep the files production-safe, minimal, and correct for a static site deployment.\n"
            f"App name: {context.app_name}\n"
            f"Project path: {context.project_path}\n"
            f"Public port: {context.exposed_port}\n"
            f"User request: {context.user_message}\n"
        )
        response = self._model_client.chat(
            messages=[{"role": "system", "content": prompt}],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        try:
            payload = json.loads(content)
            dockerfile_text = str(payload["dockerfile"])
            nginx_conf_text = str(payload["nginx_conf"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            dockerfile_text = self._fallback_static_dockerfile()
            nginx_conf_text = self._fallback_nginx_conf()

        return {
            "Dockerfile": dockerfile_text,
            "nginx.conf": nginx_conf_text,
        }

    def _execution_actions(self, context: DeploymentContext) -> list[tuple[str, dict]]:
        if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            return [
                (
                    "compose_config",
                    {
                        "action": "compose_config",
                        "project_path": context.project_path,
                    },
                ),
                (
                    "compose_up",
                    {
                        "action": "compose_up",
                        "project_path": context.project_path,
                    },
                ),
            ]

        return [
            (
                "build_image",
                {
                    "action": "build_image",
                    "image_name": context.app_name,
                    "dockerfile_path": context.project_path,
                },
            ),
            (
                "run_container",
                {
                    "action": "run_container",
                    "image_name": context.app_name,
                    "container_name": context.app_name,
                    "port_mapping": f"{context.exposed_port}:{self._container_port(context)}",
                },
            ),
        ]

    def _run_verification(self, context: DeploymentContext) -> str:
        if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            outputs = []
            for arguments in (
                {"action": "compose_ps", "project_path": context.project_path},
                {"action": "compose_logs", "project_path": context.project_path},
            ):
                tool_event, tool_output = self._docker_tool.execute(
                    server_id=context.server_id,
                    arguments=arguments,
                )
                outputs.append(tool_output)
                if tool_event.exit_status != 0:
                    break
            return self._render_verification_summary(context, outputs)

        outputs = []
        for arguments in (
            {"action": "list_containers"},
            {"action": "logs", "container_name": context.app_name},
        ):
            tool_event, tool_output = self._docker_tool.execute(
                server_id=context.server_id,
                arguments=arguments,
            )
            outputs.append(tool_output)
            if tool_event.exit_status != 0:
                break
        return self._render_verification_summary(context, outputs)

    def _is_static_site_project(self, context: DeploymentContext) -> bool:
        latest_builder_output = context.session_state.get("latest_builder_output", {})
        if latest_builder_output.get("project_path") == context.project_path:
            return True

        lowered = context.user_message.lower()
        if any(term in lowered for term in ("website", "landing page", "portfolio", "static site", "html css js")):
            return True

        index_exists = self._check_file_exists(context, "index.html")
        package_exists = self._check_file_exists(context, "package.json")
        requirements_exists = self._check_file_exists(context, "requirements.txt")
        return index_exists and not package_exists and not requirements_exists

    def _check_file_exists(self, context: DeploymentContext, filename: str) -> bool:
        if not context.project_path:
            return False
        tool_event, _ = self._docker_tool.execute(
            server_id=context.server_id,
            arguments={
                "action": "check_file",
                "target_path": f"{context.project_path.rstrip('/')}/{filename}",
            },
        )
        return tool_event.exit_status == 0

    @staticmethod
    def _container_port(context: DeploymentContext) -> int:
        if "nginx.conf" in context.generated_files:
            return 80
        return int(context.exposed_port or 80)

    def _render_cancel_message(self, context: DeploymentContext) -> str:
        return self._generate_text(
            instruction=(
                "Tell the user the pending deployment was cancelled. "
                "Be calm, concise, and reassure them that nothing was changed on the server."
            ),
            context=context,
            fallback="Okay, I cancelled the pending deployment plan. Nothing was changed on the server.",
        )

    def _render_no_pending_approval_message(self, context: DeploymentContext) -> str:
        return self._generate_text(
            instruction=(
                "Tell the user there is no deployment plan waiting for approval right now, "
                "and ask them to prepare a deployment first."
            ),
            context=context,
            fallback="There is no deployment plan waiting for approval right now. Ask me to prepare a deployment first.",
        )

    def _render_validation_message(self, context: DeploymentContext, errors: list[dict[str, str]]) -> str:
        return self._generate_text(
            instruction=(
                "You are reporting deployment validation results. "
                "Explain the blocking issues in a clear, user-friendly way and suggest that you can help fix them first."
            ),
            context=context,
            extra={
                "validation_errors": errors,
            },
            fallback=(
                "I checked the server before starting the deployment.\n\n"
                + "\n".join(f"- {item['message']}" for item in errors)
                + "\n\nIf you want, I can help you fix that first and then continue."
            ),
        )

    def _render_missing_inputs_message(self, context: DeploymentContext, missing_inputs: list[str]) -> str:
        return self._generate_text(
            instruction=(
                "You are asking the user for the missing details needed to continue a deployment. "
                "Be natural, short, and specific about what is still needed."
            ),
            context=context,
            extra={"missing_inputs": missing_inputs},
            fallback="I’m ready to prepare the deployment, but I still need: " + ", ".join(missing_inputs) + ".",
        )

    def _render_execution_failure(self, context: DeploymentContext, summary: str, tool_output: str) -> str:
        return self._generate_text(
            instruction=(
                "The deployment hit a Docker execution failure. "
                "Explain that the rollout stopped safely, summarize the likely problem clearly, "
                "and invite the user to inspect or fix it next."
            ),
            context=context,
            extra={"failure_summary": summary, "tool_output": tool_output},
            fallback=(
                f"{summary}\n\nI stopped the rollout at that point so nothing continues unexpectedly.\n\n"
                "If you want, I can help inspect the error and suggest the next safe step.\n\n"
                f"Technical details:\n{tool_output}"
            ),
        )

    def _render_approval_summary(self, context: DeploymentContext) -> str:
        return self._generate_text(
            instruction=(
                "Summarize the prepared deployment plan for approval. "
                "Explain what will be created or updated, which path and port will be used, "
                "and ask the user to reply with 'approve deployment' or 'cancel deployment'."
            ),
            context=context,
            extra={"generated_files": list(context.generated_files.keys())},
            fallback=(
                "I have prepared the deployment plan.\n\n"
                f"App: {context.app_name}\n"
                f"Mode: {self._friendly_deployment_type(context.deployment_type)}\n"
                f"Project path: {context.project_path}\n"
                f"Public port: {context.exposed_port}\n"
                f"Files to create or update: {', '.join(context.generated_files)}\n\n"
                "If you want me to continue, reply with 'approve deployment'. If you want to stop here, reply with 'cancel deployment'."
            ),
        )

    def _render_verification_summary(self, context: DeploymentContext, outputs: list[str]) -> str:
        return self._generate_text(
            instruction=(
                "Summarize the deployment verification results for the user. "
                "Interpret the Docker outputs, explain whether the deployment looks healthy, "
                "mention the expected public port, and keep it user-friendly."
            ),
            context=context,
            extra={"verification_outputs": outputs},
            fallback=(
                f"Deployment completed for '{context.app_name}'.\n\n"
                f"Expected access port: {context.exposed_port}\n\n"
                + "\n\n".join(outputs)
            ),
        )

    @staticmethod
    def _tool_called_event(action: str, command: str) -> dict:
        return {
            "type": "tool_called",
            "tool_name": "docker_action",
            "action": action,
            "command": command,
        }

    @staticmethod
    def _tool_event(tool_event) -> dict:
        return {
            "type": "tool_event",
            "tool_name": tool_event.tool_name,
            "command": tool_event.command,
            "exit_status": tool_event.exit_status,
            "stdout": tool_event.stdout,
            "stderr": tool_event.stderr,
        }

    def _detect_turn_intent(self, context: DeploymentContext) -> str:
        pending = context.pending_state or {}
        if not pending:
            return "new_request"
        payload = self._generate_json(
            instruction=(
                "Classify the user's latest deployment reply. "
                "Return JSON only with key 'intent'. "
                "Valid values: approve, cancel, continue. "
                "Use approve only if the user is clearly approving the prepared deployment. "
                "Use cancel only if the user is clearly stopping it."
            ),
            context=context,
            extra={"pending_deployment": pending},
        )
        intent = str(payload.get("intent", "continue")).strip().lower()
        if intent in {"approve", "cancel"}:
            return intent
        return "continue"

    def _extract_request_details(self, context: DeploymentContext, pending: dict) -> dict:
        payload = self._generate_json(
            instruction=(
                "Extract deployment parameters from the full conversation context. "
                "Return JSON only with keys: project_path, app_name, exposed_port. "
                "Use null for unknown values. "
                "Prefer facts already established in the recent history when they clearly refer to the current deployment request."
            ),
            context=context,
            extra={"pending_deployment": pending},
        )
        normalized: dict[str, object] = {}
        project_path = payload.get("project_path")
        if isinstance(project_path, str) and project_path.strip():
            normalized["project_path"] = project_path.strip().rstrip(".,")
        app_name = payload.get("app_name")
        if isinstance(app_name, str) and app_name.strip():
            normalized["app_name"] = app_name.strip().lower().replace(" ", "-")
        exposed_port = payload.get("exposed_port")
        if isinstance(exposed_port, int):
            normalized["exposed_port"] = exposed_port
        elif isinstance(exposed_port, str) and exposed_port.isdigit():
            normalized["exposed_port"] = int(exposed_port)
        return normalized

    def _generate_json(self, instruction: str, context: DeploymentContext, extra: dict | None = None) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's Docker deployment pipeline assistant.\n"
                    f"{instruction}\n"
                    "Return valid JSON only."
                ),
            },
            *context.history[-8:],
            {"role": "user", "content": context.user_message},
        ]
        if extra:
            messages.append({"role": "system", "content": json.dumps(extra, ensure_ascii=True)})
        response = self._model_client.chat(messages=messages, tools=[])
        content = response.get("message", {}).get("content", "") or "{}"
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _generate_text(
        self,
        instruction: str,
        context: DeploymentContext,
        fallback: str,
        extra: dict | None = None,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's Docker deployment assistant.\n"
                    f"{instruction}\n"
                    "Respond naturally, clearly, and briefly. Do not mention internal pipeline mechanics."
                ),
            },
            *context.history[-6:],
            {"role": "user", "content": context.user_message},
            {
                "role": "system",
                "content": json.dumps(
                    {
                        "deployment_type": context.deployment_type,
                        "project_path": context.project_path,
                        "app_name": context.app_name,
                        "exposed_port": context.exposed_port,
                        **(extra or {}),
                    },
                    ensure_ascii=True,
                ),
            },
        ]
        response = self._model_client.chat(messages=messages, tools=[])
        content = (response.get("message", {}).get("content", "") or "").strip()
        return content or fallback

    @staticmethod
    def _derive_app_name(project_path: str | None) -> str:
        if project_path:
            return project_path.rstrip("/").split("/")[-1].lower().replace("_", "-")
        return "app-service"

    @staticmethod
    def _friendly_deployment_type(deployment_type: str) -> str:
        if deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            return "Docker Compose deployment"
        if deployment_type == DEPLOYMENT_TYPE_DOCKER_SINGLE:
            return "Single-container Docker deployment"
        return deployment_type.replace("_", " ").title()

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix

    @staticmethod
    def _fallback_compose(context: DeploymentContext) -> str:
        return (
            "services:\n"
            f"  {context.app_name}:\n"
            "    build:\n"
            "      context: .\n"
            "      dockerfile: Dockerfile\n"
            "    restart: unless-stopped\n"
            f"    ports:\n      - \"{context.exposed_port}:{context.exposed_port}\"\n"
        )

    @staticmethod
    def _fallback_dockerfile() -> str:
        return (
            "FROM python:3.13-slim\n"
            "WORKDIR /app\n"
            "COPY . /app\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "CMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n"
        )

    @staticmethod
    def _fallback_static_dockerfile() -> str:
        return (
            "FROM nginx:1.27-alpine\n"
            "COPY nginx.conf /etc/nginx/conf.d/default.conf\n"
            "COPY . /usr/share/nginx/html\n"
            "EXPOSE 80\n"
            'CMD ["nginx", "-g", "daemon off;"]\n'
        )

    @staticmethod
    def _fallback_nginx_conf() -> str:
        return (
            "server {\n"
            "    listen 80;\n"
            "    server_name _;\n"
            "    root /usr/share/nginx/html;\n"
            "    index index.html;\n\n"
            "    location / {\n"
            "        try_files $uri $uri/ /index.html;\n"
            "    }\n"
            "}\n"
        )
