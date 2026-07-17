from collections.abc import Iterator

from src.deployments.docker_pipeline import DockerDeploymentPipeline
from src.deployments.models import DeploymentContext, DeploymentState
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import SkillContext
from src.tools.docker_tools import DockerTool
from src.tools.ssh_tool import SSHCommandTool
from src.deployments.preparation import (apply_preparation_details, extract_root_path, extract_preparation_details, needs_port, needs_preparation_prompt, needs_project_selection, render_discovery_failure, render_discovery_result, render_port_prompt, render_preparation_question, render_project_selection_prompt, resolve_directory_selection, select_deployment_type, should_inspect_directories, stream_message)
from src.deployments.utils import chunk_text, directory_discovery_command, parse_directories


class DeploymentEngine:
    def __init__(
        self,
        model_client: OllamaModelClient,
        docker_tool: DockerTool,
        ssh_tool: SSHCommandTool,
    ) -> None:
        self._model_client = model_client
        self._docker_pipeline = DockerDeploymentPipeline(
            model_client=model_client,
            docker_tool=docker_tool,
        )
        self._ssh_tool = ssh_tool

    def stream(self, context: SkillContext) -> Iterator[dict]:
        deployment_type = select_deployment_type(self._model_client, context)
        state = DeploymentState.from_session(context.session_state) or DeploymentState()
        if not state.deployment_type:
            state.deployment_type = deployment_type
        state.persist(context.session_state)
        deployment_context = DeploymentContext(
            session_id=context.session_id,
            server_id=context.server_id,
            user_message=context.user_message,
            history=context.history,
            session_state=context.session_state,
            state=state,
        )
        extracted = extract_preparation_details(self._model_client, deployment_context)
        apply_preparation_details(deployment_context, extracted)

        if should_inspect_directories(deployment_context.state, extracted):
            yield from self._inspect_directories(deployment_context)
            return

        selected_path = resolve_directory_selection(deployment_context, extracted)
        if selected_path:
            deployment_context.project_path = selected_path

        deployment_context.save_state()

        if needs_preparation_prompt(deployment_context):
            yield from stream_message(render_preparation_question(self._model_client, deployment_context))
            return

        if needs_project_selection(deployment_context):
            yield from stream_message(render_project_selection_prompt(self._model_client, deployment_context, deployment_context.state.get("suggested_directories", [])))
            return

        if needs_port(deployment_context):
            yield from stream_message(render_port_prompt(self._model_client, deployment_context, deployment_context.project_path or "that project"))
            return

        yield from self._docker_pipeline.stream(deployment_context)


    def _inspect_directories(self, context: DeploymentContext) -> Iterator[dict]:
        root_path = extract_root_path(context.user_message) or context.state.get("root_path") or "~/shellmate-sites"
        context.state["root_path"] = root_path

        yield {
            "type": "step_started",
            "step": "deployment_discovery",
            "detail": "Inspecting likely project directories on the server.",
        }
        tool_event, tool_output = self._ssh_tool.execute(
            server_id=context.server_id,
            arguments={
                "command": directory_discovery_command(root_path),
                "reason": "List likely project directories before deployment.",
            },
        )
        yield {
            "type": "tool_called",
            "tool_name": tool_event.tool_name,
            "command": tool_event.command,
        }
        yield {
            "type": "tool_event",
            "tool_name": tool_event.tool_name,
            "command": tool_event.command,
            "exit_status": tool_event.exit_status,
            "stdout": tool_event.stdout,
            "stderr": tool_event.stderr,
        }
        if tool_event.exit_status != 0:
            yield {
                "type": "step_completed",
                "step": "deployment_discovery",
                "detail": "Directory inspection failed.",
            }
            for token in chunk_text(
                render_discovery_failure(self._model_client, context, root_path, tool_output)
            ):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        directories = parse_directories(tool_event.stdout)
        context.state["suggested_directories"] = directories
        context.state["awaiting_directory_selection"] = True
        context.save_state()

        yield {
            "type": "step_completed",
            "step": "deployment_discovery",
            "detail": "Directory inspection completed.",
        }

        message = render_discovery_result(self._model_client, context, root_path, directories)
        for token in chunk_text(message):
            yield {"type": "token", "content": token}
        yield {"type": "done"}
