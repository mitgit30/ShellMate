"""Pure helpers shared by deployment workflows."""

import json
from collections.abc import Iterator


def safe_json(payload: dict) -> str:
    return json.dumps(_json_ready(payload), ensure_ascii=True)

def _json_ready(value: object, path: str = "$") -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_ready(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if hasattr(value, "to_dict"):
        return _json_ready(value.to_dict(), path)
    if isinstance(value, property):
        raise TypeError(f"Property descriptor found at {path}; deployment state contains an invalid field.")
    raise TypeError(f"Object of type {type(value).__name__} at {path} is not JSON serializable.")

def chunk_text(text: str) -> Iterator[str]:
    words = text.split(" ")
    for index, word in enumerate(words):
        suffix = " " if index < len(words) - 1 else ""
        yield word + suffix


def directory_discovery_command(root_path: str) -> str:
    if root_path == "~":
        resolved = "$HOME"
    elif root_path.startswith("~/"):
        resolved = f"$HOME/{root_path[2:]}"
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


def parse_directories(stdout: str) -> list[str]:
    directories: list[str] = []
    for line in stdout.splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("__SHELLMATE_MISSING_ROOT__:"):
            directories.append(cleaned)
    return directories


def derive_app_name(project_path: str | None) -> str:
    if project_path:
        return project_path.rstrip("/").split("/")[-1].lower().replace("_", "-")
    return "app-service"


def friendly_deployment_type(deployment_type: str) -> str:
    if deployment_type == "docker_compose_app":
        return "Docker Compose deployment"
    if deployment_type == "docker_single_app":
        return "Single-container Docker deployment"
    return deployment_type.replace("_", " ").title()