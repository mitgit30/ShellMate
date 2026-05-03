from backend.app.schemas.command import CommandExecutionResponse
from backend.app.services.ssh_service import SSHService
from src.runtime.models import ToolEvent


class WebDevTool:
    name = "web_dev_action"
    schema = {
        "type": "function",
        "function": {
            "name": "web_dev_action",
            "description": (
                "Create and serve a web project (HTML, CSS, JS) on the server. "
                "Writes files and optionally starts a web server accessible via public IP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["create_files", "run_server"],
                    },
                    "project_name": {
                        "type": "string",
                    },
                    "html": {"type": "string"},
                    "css": {"type": "string"},
                    "js": {"type": "string"},
                    "port": {
                        "type": "number",
                        "default": 5000,
                    },
                },
                "required": ["action", "project_name"],
            },
        },
    }

    def __init__(self, ssh_service: SSHService) -> None:
        self._ssh_service = ssh_service

    def execute(self, server_id: str, arguments: dict) -> tuple[ToolEvent, str]:
        action = arguments.get("action")
        project = arguments.get("project_name")

        if action == "create_files":
            html = arguments.get("html", "")
            css = arguments.get("css", "")
            js = arguments.get("js", "")

            command = f"""
            mkdir -p {project} && cd {project} &&
            cat << 'EOF' > index.html
            {html}
            EOF
            cat << 'EOF' > styles.css
            {css}
            EOF
            cat << 'EOF' > script.js
            {js}
            EOF
"""

        elif action == "run_server":
            port = arguments.get("port", 5000)

            command = f"""
                # Kill any existing server on same port (optional safety)
                pkill -f "http.server {port}" || true

                # Get public IP
                PUBLIC_IP=$(curl -s ifconfig.me)

                # Start server in background
                cd {project} && nohup python3 -m http.server {port} --bind 0.0.0.0 > server.log 2>&1 &

                # Output access URL
                echo "LIVE_URL: http://$PUBLIC_IP:{port}"
            """

        else:
            raise ValueError("Invalid action")

        response = self._ssh_service.execute_command(
            server_id=server_id,
            command=command,
        )

        return self._to_tool_event(response), self._format_tool_result(response, arguments)

    @staticmethod
    def _to_tool_event(response: CommandExecutionResponse) -> ToolEvent:
        return ToolEvent(
            tool_name="web_dev_action",
            command=response.command,
            exit_status=response.exit_status,
            stdout=response.stdout,
            stderr=response.stderr,
        )

    @staticmethod
    def _format_tool_result(response: CommandExecutionResponse, arguments: dict) -> str:
        port = arguments.get("port", 5000)

        return (
            f"Command: {response.command}\n"
            f"Exit status: {response.exit_status}\n\n"
            f" STDOUT:\n{response.stdout or '<empty>'}\n\n"
            f" STDERR:\n{response.stderr or '<empty>'}\n\n"
            f" If successful, your site should be live at:\n"
            f"(Check for LIVE_URL above)\n\n"
            f" If not working, verify:\n"
            f"1. Port {port} is open in firewall / security group\n"
            f"2. Server is running (ps aux | grep http.server)\n"
            f"3. App is bound to 0.0.0.0\n"
        )