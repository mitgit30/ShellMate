from backend.app.schemas.command import CommandExecutionResponse
from backend.app.services.ssh_service import SSHService
from src.runtime.models import ToolEvent


class SSHCommandTool:
    name = "run_ssh_command"
    schema = {
        "type": "function",
        "function": {
            "name": "run_ssh_command",
            "description": (
                "Run a Linux command on the currently connected server over SSH. "
                "Use this when real server data is needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Exact Linux command to run on the server.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Short reason for running the command.",
                    },
                },
                "required": ["command"],
            },
        },
    }

    def __init__(self, ssh_service: SSHService) -> None:
        self._ssh_service = ssh_service

    def execute(self, server_id: str, arguments: dict) -> tuple[ToolEvent, str]:
        command = str(arguments.get("command", "")).strip()
        if not command:
            raise ValueError("run_ssh_command requires a non-empty command.")

        response = self._ssh_service.execute_command(server_id=server_id, command=command)
        return self._to_tool_event(response), self._format_tool_result(response)

    @staticmethod
    def _to_tool_event(response: CommandExecutionResponse) -> ToolEvent:
        return ToolEvent(
            tool_name="run_ssh_command",
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
