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
                            "build_image",
                            "run_container",
                            "stop_container",
                            "remove_container",
                            "logs",
                            "list_containers",
                        ],
                    },
                    "image_name": {"type": "string"},
                    "container_name": {"type": "string"},
                    "dockerfile_path": {"type": "string"},
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

        if action == "build_image":
            image = arguments.get("image_name")
            path = arguments.get("dockerfile_path", ".")
            command = f"docker build -t {image} {path}"

        elif action == "run_container":
            image = arguments.get("image_name")
            name = arguments.get("container_name")
            port = arguments.get("port_mapping", "")
            port_flag = f"-p {port}" if port else ""
            command = f"docker run -d --name {name} {port_flag} {image}"

        elif action == "stop_container":
            name = arguments.get("container_name")
            command = f"docker stop {name}"

        elif action == "remove_container":
            name = arguments.get("container_name")
            command = f"docker rm {name}"

        elif action == "logs":
            name = arguments.get("container_name")
            command = f"docker logs {name}"

        elif action == "list_containers":
            command = "docker ps -a"

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