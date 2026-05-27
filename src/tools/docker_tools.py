import shlex

from backend.app.schemas.command import CommandExecutionResponse
from backend.app.services.ssh_service import SSHService
from src.runtime.models import ToolEvent


class DockerTool:
    name = "docker_action"
    schema = {
        "type": "function",
        "function": {
            "name": "docker_action",
            "description": "Execute Docker operations on remote server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "check_docker",
                            "check_compose",
                            "check_directory",
                            "check_file",
                            "check_port_free",
                            "write_file",
                            "build_image",
                            "run_container",
                            "stop_container",
                            "remove_container",
                            "logs",
                            "list_containers",
                            "compose_config",
                            "compose_up",
                            "compose_ps",
                            "compose_logs",
                        ],
                    },
                    "image_name": {"type": "string"},
                    "container_name": {"type": "string"},
                    "dockerfile_path": {"type": "string"},
                    "project_path": {"type": "string"},
                    "target_path": {"type": "string"},
                    "content": {"type": "string"},
                    "port": {"type": "integer"},
                    "port_mapping": {
                        "type": "string",
                        "description": "Format: host_port:container_port",
                    },
                },
                "required": ["action"],
            },
        },
    }

    def __init__(self, ssh_service: SSHService) -> None:
        self._ssh_service = ssh_service

    def execute(self, server_id: str, arguments: dict):
        action = arguments.get("action")

        if action == "check_docker":
            command = "docker --version"

        elif action == "check_compose":
            command = "docker compose version"

        elif action == "check_directory":
            path = self._require_argument(arguments, "target_path")
            command = f"test -d {shlex.quote(path)}"

        elif action == "check_file":
            path = self._require_argument(arguments, "target_path")
            command = f"test -f {shlex.quote(path)}"

        elif action == "check_port_free":
            port = int(self._require_argument(arguments, "port"))
            command = (
                "sh -lc "
                + shlex.quote(
                    f"! ss -tulpn | grep -E ':{port}\\b' >/dev/null"
                )
            )

        elif action == "write_file":
            target_path = self._require_argument(arguments, "target_path")
            content = str(arguments.get("content", ""))
            target_dir = target_path.rsplit("/", 1)[0] if "/" in target_path else "."
            command = (
                f"mkdir -p {shlex.quote(target_dir)} && "
                f"cat <<'EOF' > {shlex.quote(target_path)}\n"
                f"{content}\n"
                "EOF"
            )

        elif action == "build_image":
            image = arguments.get("image_name")
            path = arguments.get("dockerfile_path", ".")
            command = f"docker build -t {shlex.quote(image)} {shlex.quote(path)}"

        elif action == "run_container":
            image = arguments.get("image_name")
            name = arguments.get("container_name")
            port = arguments.get("port_mapping", "")
            port_flag = f"-p {shlex.quote(port)}" if port else ""
            command = (
                f"docker run -d --name {shlex.quote(name)} "
                f"{port_flag} {shlex.quote(image)}"
            )

        elif action == "stop_container":
            name = arguments.get("container_name")
            command = f"docker stop {shlex.quote(name)}"

        elif action == "remove_container":
            name = arguments.get("container_name")
            command = f"docker rm {shlex.quote(name)}"

        elif action == "logs":
            name = arguments.get("container_name")
            command = f"docker logs {shlex.quote(name)}"

        elif action == "list_containers":
            command = "docker ps -a"

        elif action == "compose_config":
            project_path = self._require_argument(arguments, "project_path")
            command = f"cd {shlex.quote(project_path)} && docker compose config"

        elif action == "compose_up":
            project_path = self._require_argument(arguments, "project_path")
            command = f"cd {shlex.quote(project_path)} && docker compose up -d --build"

        elif action == "compose_ps":
            project_path = self._require_argument(arguments, "project_path")
            command = f"cd {shlex.quote(project_path)} && docker compose ps"

        elif action == "compose_logs":
            project_path = self._require_argument(arguments, "project_path")
            command = f"cd {shlex.quote(project_path)} && docker compose logs --tail 50"

        else:
            raise ValueError("Invalid Docker action")

        response = self._ssh_service.execute_command(
            server_id=server_id,
            command=command,
        )

        return self._to_tool_event(response), self._format_tool_result(response)

    @staticmethod
    def _to_tool_event(response: CommandExecutionResponse) -> ToolEvent:
        return ToolEvent(
            tool_name="docker_action",
            command=response.command,
            exit_status=response.exit_status,
            stdout=response.stdout,
            stderr=response.stderr,
        )

    @staticmethod
    def _format_tool_result(response: CommandExecutionResponse) -> str:
        return (
            f"Command: {response.command}\n"
            f"Exit status: {response.exit_status}\n"
            f"STDOUT:\n{response.stdout or '<empty>'}\n"
            f"STDERR:\n{response.stderr or '<empty>'}"
        )

    @staticmethod
    def _require_argument(arguments: dict, key: str):
        value = arguments.get(key)
        if value in (None, ""):
            raise ValueError(f"docker_action requires '{key}'.")
        return value
