
# Helper module for builder_skill , if needed then it will call the builder tools
import re
import shlex

from backend.app.schemas.command import CommandExecutionResponse
from backend.app.services.ssh_service import SSHService
from src.runtime.models import ToolEvent


class BuilderTool:
    def __init__(self, ssh_service: SSHService) -> None:
        self._ssh_service = ssh_service

    def write_static_site(self, server_id: str, project_path: str, files: dict[str, str]) -> tuple[ToolEvent, str]:
        if not project_path.strip():
            raise ValueError("project_path is required for builder site creation.")
        if not files:
            raise ValueError("files are required for builder site creation.")

        command_parts = [self._target_dir_assignment(project_path), 'mkdir -p "$TARGET_DIR"', 'cd "$TARGET_DIR"']
        for filename, content in files.items():
            safe_filename = shlex.quote(filename)
            command_parts.append(f"cat <<'EOF' > {safe_filename}\n{content}\nEOF")
        command_parts.append('printf "SHELLMATE_SITE_PATH=%s\\n" "$TARGET_DIR"')
        command_parts.append("pwd")
        command_parts.append("ls -1")

        command = "\n".join(command_parts)
        response = self._ssh_service.execute_command(server_id=server_id, command=command)
        return self._to_tool_event(response), self._format_tool_result(response)

    @staticmethod
    def suggest_folder_name(user_message: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", user_message.lower()).strip("-")
        cleaned = cleaned[:40] or "shellmate-site"
        return f"shellmate-{cleaned}"

    @staticmethod
    def extract_saved_path(stdout: str) -> str | None:
        match = re.search(r"^SHELLMATE_SITE_PATH=(.+)$", stdout, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    @staticmethod
    def _target_dir_assignment(project_path: str) -> str:
        if project_path == "~":
            return 'TARGET_DIR="$HOME"'
        if project_path.startswith("~/"):
            remainder = project_path[2:]
            return f'TARGET_DIR="$HOME"/{shlex.quote(remainder)}'
        return f"TARGET_DIR={shlex.quote(project_path)}"

    @staticmethod
    def _to_tool_event(response: CommandExecutionResponse) -> ToolEvent:
        return ToolEvent(
            tool_name="builder_write_site",
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
