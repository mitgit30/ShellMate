import json
import re
from collections.abc import Iterator

from src.deployments.models import (
    DEPLOYMENT_TYPE_DOCKER_COMPOSE,
    DEPLOYMENT_TYPE_DOCKER_SINGLE,
    DeploymentContext,
    DeploymentState,
)
from src.deployments.utils import safe_json
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import SkillContext


def extract_root_path(user_message: str) -> str | None:
    match = re.search(r"(?:check|inspect|scan|search|look in|directory)\s+(?:the\s+)?([~/.\w-]+)", user_message, re.IGNORECASE)
    return match.group(1).strip().rstrip(".,") if match else None


def should_inspect_directories(state: DeploymentState, extracted: dict) -> bool:
    intent = str(extracted.get("prep_intent", "")).strip().lower()
    return intent == "inspect_directories" or (
        state.get("awaiting_directory_selection") and intent == "continue_directory_help"
    )


def needs_preparation_prompt(context: DeploymentContext) -> bool:
    lowered = context.user_message.lower()
    return not context.project_path and any(
        term in lowered for term in ("deploy", "deployment", "docker", "publish", "ship")
    )


def needs_project_selection(context: DeploymentContext) -> bool:
    return bool(context.state.get("awaiting_directory_selection")) and not context.project_path


def needs_port(context: DeploymentContext) -> bool:
    return context.project_path is not None and context.exposed_port is None


def resolve_directory_selection(context: DeploymentContext, extracted: dict) -> str | None:
    explicit_path = extracted.get("project_path")
    if isinstance(explicit_path, str) and explicit_path.strip():
        resolved = explicit_path.strip().rstrip(".,")
        context.state["awaiting_directory_selection"] = False
        context.state["project_path"] = resolved
        if extracted.get("app_name"):
            context.state["app_name"] = str(extracted["app_name"]).strip().lower().replace("_", "-")
        return resolved

    directories = context.state.get("suggested_directories", [])
    selected_name = str(extracted.get("selected_directory_name", "")).strip().lower()
    for directory in directories:
        basename = directory.rstrip("/").split("/")[-1].lower()
        if basename and selected_name and basename == selected_name:
            context.state["awaiting_directory_selection"] = False
            context.state["project_path"] = directory
            context.state["app_name"] = basename.replace("_", "-")
            return directory
    return None


def apply_preparation_details(context: DeploymentContext, extracted: dict) -> None:
    if extracted.get("project_path"):
        context.project_path = str(extracted["project_path"])
    if extracted.get("app_name"):
        context.app_name = str(extracted["app_name"]).lower().replace(" ", "-")
    if extracted.get("exposed_port") is not None:
        context.exposed_port = int(extracted["exposed_port"])
    if extracted.get("root_path"):
        context.state["root_path"] = str(extracted["root_path"])


def select_deployment_type(model_client: OllamaModelClient, context: SkillContext) -> str:
    state = DeploymentState.from_session(context.session_state)
    if state and state.deployment_type:
        return str(state.deployment_type)
    payload = generate_json(
        model_client,
        instruction=(
            "Choose the deployment type for this request. "
            "Return JSON only with key deployment_type. "
            "Valid values: docker_single_app, docker_compose_app. "
            "Use docker_compose_app for multi-service, compose, MERN, or LAMP style deployments. "
            "Otherwise use docker_single_app."
        ),
        history=context.history,
        user_message=context.user_message,
        extra={"session_state": context.session_state},
    )
    deployment_type = str(payload.get("deployment_type", DEPLOYMENT_TYPE_DOCKER_SINGLE)).strip()
    return deployment_type if deployment_type in {DEPLOYMENT_TYPE_DOCKER_COMPOSE, DEPLOYMENT_TYPE_DOCKER_SINGLE} else DEPLOYMENT_TYPE_DOCKER_SINGLE


def extract_preparation_details(model_client: OllamaModelClient, context: DeploymentContext) -> dict:
    payload = generate_json(
        model_client,
        instruction=(
            "Extract deployment preparation details from the full conversation context. "
            "Return JSON only with keys: prep_intent, project_path, app_name, exposed_port, root_path, selected_directory_name. "
            "Valid prep_intent values: inspect_directories, continue_directory_help, provide_details, ask_for_preparation, continue. "
            "Use null for unknown values. "
            "Prefer conversation history and existing deployment metadata when they clearly refer to the same task."
        ),
        history=context.history,
        user_message=context.user_message,
        extra={"deployment_state": context.state.to_dict()},
    )
    normalized = {key: value.strip().rstrip(".,") for key in ("prep_intent", "project_path", "app_name", "root_path", "selected_directory_name") if isinstance(value := payload.get(key), str) and value.strip()}
    exposed_port = payload.get("exposed_port")
    if isinstance(exposed_port, int):
        normalized["exposed_port"] = exposed_port
    elif isinstance(exposed_port, str) and exposed_port.isdigit():
        normalized["exposed_port"] = int(exposed_port)
    return normalized


def generate_json(model_client: OllamaModelClient, instruction: str, history: list[dict], user_message: str, extra: dict | None = None) -> dict:
    messages = [
        {"role": "system", "content": f"You are ShellMate's deployment preparation assistant.\n{instruction}\nReturn valid JSON only."},
        *history[-8:],
        {"role": "user", "content": user_message},
    ]
    if extra:
        messages.append({"role": "system", "content": safe_json(extra)})
    response = model_client.chat(messages=messages, tools=[])
    content = response.get("message", {}).get("content", "") or "{}"
    try:
        payload = json.loads(content)
        return payload if isinstance(payload, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def generate_text(model_client: OllamaModelClient, instruction: str, context: DeploymentContext, fallback: str, extra: dict | None = None) -> str:
    messages = [
        {"role": "system", "content": f"You are ShellMate's deployment preparation assistant.\n{instruction}\nRespond naturally, clearly, and briefly. Do not mention internal pipeline mechanics."},
        *context.history[-6:],
        {"role": "user", "content": context.user_message},
        {"role": "system", "content": safe_json({"deployment_type": context.deployment_type, "project_path": context.project_path, "app_name": context.app_name, "exposed_port": context.exposed_port, "deployment_state": context.state.to_dict(), **(extra or {})})},
    ]
    response = model_client.chat(messages=messages, tools=[])
    return (response.get("message", {}).get("content", "") or "").strip() or fallback


def render_discovery_failure(model_client: OllamaModelClient, context: DeploymentContext, root_path: str, tool_output: str) -> str:
    return generate_text(model_client, "The directory discovery step failed. Explain that you could not inspect the requested server location, mention the root path briefly, and suggest giving the exact project path directly.", context, "I couldn't inspect that server location yet.\n\nIf you want, send me the exact project path directly and I can continue from there.\n\nTechnical details:\n" + tool_output, {"root_path": root_path, "tool_output": tool_output})


def render_discovery_result(model_client: OllamaModelClient, context: DeploymentContext, root_path: str, directories: list[str]) -> str:
    fallback = (f"I checked `{root_path}` and found these likely project directories:\n\n" + "\n".join(f"- `{directory}`" for directory in directories[:8]) + "\n\nSend me the directory you want to deploy, and include the public port if you already know it.") if directories else f"I checked `{root_path}`, but I didn't find any immediate subdirectories to deploy from.\n\nIf you already know the project path, send it directly and I’ll continue."
    return generate_text(model_client, "Summarize the result of directory discovery for deployment preparation. If directories were found, present them clearly and ask the user which one to deploy. If none were found, say so and ask for the exact path.", context, fallback, {"root_path": root_path, "directories": directories[:8]})


def render_preparation_question(model_client: OllamaModelClient, context: DeploymentContext) -> str:
    return generate_text(model_client, "Ask the user whether you should inspect the server for likely project directories first, or whether they want to provide the exact project path directly.", context, "I can help with that. Before I prepare the deployment, should I inspect the server and look for likely project directories first?\n\nIf yes, tell me something like `check ~/shellmate-sites` or `inspect the home directory`.\nIf you already know the exact project path, send it directly along with the public port.", {"deployment_state": context.state.to_dict()})


def render_project_selection_prompt(model_client: OllamaModelClient, context: DeploymentContext, directories: list[str]) -> str:
    return generate_text(model_client, "Ask the user to choose which directory should be deployed. Use the discovered directories when available and keep the prompt natural.", context, "I still need the project directory before I can prepare the deployment.\n\nSend the full path and, if you know it, the public port you want to expose.", {"directories": directories[:8]})


def render_port_prompt(model_client: OllamaModelClient, context: DeploymentContext, app_target: str) -> str:
    return generate_text(model_client, "Ask the user for the public port to expose for the deployment. Mention that you already have the project path.", context, f"I’ve got the project path for `{app_target}`.\n\nNow send me the public port you want to expose, for example `port 3000`.", {"app_target": app_target})


def stream_message(message: str) -> Iterator[dict]:
    words = message.split(" ")
    for index, word in enumerate(words):
        suffix = " " if index < len(words) - 1 else ""
        yield {"type": "token", "content": word + suffix}
    yield {"type": "done"}