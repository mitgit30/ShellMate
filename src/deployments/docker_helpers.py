from src.deployments.models import DEPLOYMENT_TYPE_DOCKER_COMPOSE, DeploymentContext


def execution_actions(context: DeploymentContext) -> list[tuple[str, dict]]:
    if context.deployment_type == DEPLOYMENT_TYPE_DOCKER_COMPOSE:
        return [
            ("compose_config", {"action": "compose_config", "project_path": context.project_path}),
            ("compose_up", {"action": "compose_up", "project_path": context.project_path}),
        ]
    return [
        ("build_image", {"action": "build_image", "image_name": context.app_name, "dockerfile_path": context.project_path}),
        ("run_container", {"action": "run_container", "image_name": context.app_name, "container_name": context.app_name, "port_mapping": f"{context.exposed_port}:{container_port(context)}"}),
    ]


def container_port(context: DeploymentContext) -> int:
    return 80 if "nginx.conf" in context.generated_files else int(context.exposed_port or 80)


def is_static_site_request(context: DeploymentContext) -> bool:
    latest_builder_output = context.session_state.get("latest_builder_output", {})
    if latest_builder_output.get("project_path") == context.project_path:
        return True
    lowered = context.user_message.lower()
    return any(term in lowered for term in ("website", "landing page", "portfolio", "static site", "html css js"))


def normalize_request_details(payload: dict) -> dict[str, object]:
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


def tool_called_event(action: str, command: str) -> dict:
    return {"type": "tool_called", "tool_name": "docker_action", "action": action, "command": command}


def tool_event_payload(tool_event) -> dict:
    return {"type": "tool_event", "tool_name": tool_event.tool_name, "command": tool_event.command, "exit_status": tool_event.exit_status, "stdout": tool_event.stdout, "stderr": tool_event.stderr}


def fallback_compose(context: DeploymentContext) -> str:
    return "services:\n" f"  {context.app_name}:\n" "    build:\n" "      context: .\n" "      dockerfile: Dockerfile\n" "    restart: unless-stopped\n" f"    ports:\n      - \"{context.exposed_port}:{context.exposed_port}\"\n"


def fallback_dockerfile() -> str:
    return "FROM python:3.13-slim\nWORKDIR /app\nCOPY . /app\nRUN pip install --no-cache-dir -r requirements.txt\nCMD [\"python\", \"-m\", \"http.server\", \"8000\"]\n"


def fallback_static_dockerfile() -> str:
    return "FROM nginx:1.27-alpine\nCOPY nginx.conf /etc/nginx/conf.d/default.conf\nCOPY . /usr/share/nginx/html\nEXPOSE 80\nCMD [\"nginx\", \"-g\", \"daemon off;\"]\n"


def fallback_nginx_conf() -> str:
    return "server {\n    listen 80;\n    server_name _;\n    root /usr/share/nginx/html;\n    index index.html;\n\n    location / {\n        try_files $uri $uri/ /index.html;\n    }\n}\n"