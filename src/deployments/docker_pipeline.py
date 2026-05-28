import json
import re
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
        if self._is_cancel_message(context.user_message):
            context.clear_pending()
            for token in self._chunk_text(
                "Okay, I cancelled the pending deployment plan. Nothing was changed on the server."
            ):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        if self._is_approval_message(context.user_message):
            yield from self._resume_after_approval(context)
            return

        pending = context.pending_state or {}
        context.project_path = self._extract_project_path(context.user_message)
        context.exposed_port = self._extract_port(context.user_message)
        context.app_name = self._extract_app_name(context.user_message, context.project_path)

        if context.project_path is None:
            context.project_path = pending.get("project_path")
        if context.exposed_port is None:
            context.exposed_port = pending.get("exposed_port")
        if context.app_name == "app-service" and pending.get("app_name"):
            context.app_name = pending.get("app_name")

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

            for token in self._chunk_text(
                self._format_validation_message(validation_errors)
            ):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        yield {
            "type": "step_completed",
            "step": "deployment_validate",
            "detail": "Validation checks passed.",
        }

        missing_inputs: list[str] = []
        if not context.project_path: # 
            
            missing_inputs.append("project path")
        if not context.exposed_port:
            missing_inputs.append("port to expose")

        if missing_inputs:
            question = self._format_missing_inputs_message(missing_inputs)
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
        summary = self._build_approval_summary(context)

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
            for token in self._chunk_text(
                "There is no deployment plan waiting for approval right now. Ask me to prepare a deployment first."
            ):
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
                for token in self._chunk_text(
                    self._format_execution_failure(
                        "I wasn't able to prepare the deployment files on the server.",
                        tool_output,
                    )
                ):
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
                for token in self._chunk_text(
                    self._format_execution_failure(
                        "The deployment started, but one of the Docker steps failed.",
                        tool_output,
                    )
                ):
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

    def _run_validation(self, context: DeploymentContext) -> list[str]:
        checks: list[tuple[str, dict]] = [
            ("docker", {"action": "check_docker"}),
            ("project_path", {"action": "check_directory", "target_path": context.project_path}),
        ]

        if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            checks.append(("compose", {"action": "check_compose"}))

        if context.exposed_port:
            checks.append(("port", {"action": "check_port_free", "port": context.exposed_port}))

        errors: list[str] = []
        for check_name, arguments in checks:
            if check_name == "project_path" and arguments.get("target_path") is None:
                continue
            tool_event, _ = self._docker_tool.execute(server_id=context.server_id, arguments=arguments)

            if tool_event.exit_status != 0:
                if check_name == "docker":
                    errors.append("Docker is not installed or not reachable on the server.")
                elif check_name == "compose":
                    errors.append("Docker Compose is not available on the server.")
                elif check_name == "project_path":
                    errors.append(f"Project directory '{context.project_path}' was not found.")
                elif check_name == "port":
                    errors.append(f"Port {context.exposed_port} is already in use.")

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
                    "port_mapping": f"{context.exposed_port}:{context.exposed_port}",
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
            return (
                f"Deployment completed for '{context.app_name}'.\n\n"
                f"Expected access port: {context.exposed_port}\n\n"
                + "\n\n".join(outputs)
            )

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
        return (
            f"Deployment completed for container '{context.app_name}'.\n\n"
            f"Expected access port: {context.exposed_port}\n\n"
            + "\n\n".join(outputs)
        )

    def _build_approval_summary(self, context: DeploymentContext) -> str:
        file_list = ", ".join(context.generated_files)
        return (
            "I have prepared the deployment plan.\n\n"
            f"App: {context.app_name}\n"
            f"Mode: {self._friendly_deployment_type(context.deployment_type)}\n"
            f"Project path: {context.project_path}\n"
            f"Public port: {context.exposed_port}\n"
            f"Files to create or update: {file_list}\n\n"
            "If you want me to continue, reply with 'approve deployment'. "
            "If you want to stop here, reply with 'cancel deployment'."
        )

    @staticmethod
    def _format_validation_message(errors: list[str]) -> str:
        if len(errors) == 1:
            return (
                "I checked the server before starting the deployment.\n\n"
                f"{errors[0]}\n\n"
                "If you want, I can help you fix that first and then continue."
            )

        return (
            "I checked the server before starting the deployment, and a few things need attention first:\n\n- "
            + "\n- ".join(errors)
            + "\n\nOnce these are fixed, I can continue with the deployment."
        )

    @staticmethod
    def _format_missing_inputs_message(missing_inputs: list[str]) -> str:
        if len(missing_inputs) == 1:
            return (
                "I’m ready to prepare the deployment, but I still need one detail from you: "
                f"{missing_inputs[0]}."
            )

        return (
            "I’m ready to prepare the deployment, but I still need these details from you: "
            + ", ".join(missing_inputs)
            + "."
        )

    @staticmethod
    def _format_execution_failure(summary: str, tool_output: str) -> str:
        return (
            f"{summary}\n\n"
            "I stopped the rollout at that point so nothing continues unexpectedly.\n\n"
            "If you want, I can help inspect the error and suggest the next safe step.\n\n"
            f"Technical details:\n{tool_output}"
        )

    @staticmethod
    def _friendly_deployment_type(deployment_type: str) -> str:
        if deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
            return "Docker Compose deployment"
        if deployment_type == DEPLOYMENT_TYPE_DOCKER_SINGLE:
            return "Single-container Docker deployment"
        return deployment_type.replace("_", " ").title()

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

    @staticmethod
    def _extract_project_path(message: str) -> str | None:
        match = re.search(
            r"(?:path|directory|project)(?:\s+path)?\s+(?:is\s+|at\s+)?([~/.\w\-/]+)",
            message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().rstrip(".,")
        return None

    @staticmethod
    def _extract_port(message: str) -> int | None:
        match = re.search(r"\bport\b\s*[:=\-]?\s*(\d{2,5})\b", message, re.IGNORECASE)
        if match:
            return int(match.group(1))
        fallback = re.search(r"\b(?:on|at)\s+port\s*(\d{2,5})\b", message, re.IGNORECASE)
        if fallback:
            return int(fallback.group(1))
        return None

    @staticmethod
    def _extract_app_name(message: str, project_path: str | None) -> str:
        match = re.search(
            r"(?:(?:app|service)\s+(?:name|named)|project\s+name)\s+([a-zA-Z0-9_-]+)",
            message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower()
        if project_path:
            return project_path.rstrip("/").split("/")[-1].lower().replace("_", "-")
        return "app-service"

    @staticmethod
    def _is_approval_message(message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ("approve deployment", "approve", "yes proceed", "yes deploy", "confirm deployment"))

    @staticmethod
    def _is_cancel_message(message: str) -> bool:
        lowered = message.lower()
        return any(term in lowered for term in ("cancel deployment", "stop deployment", "abort deployment"))

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
