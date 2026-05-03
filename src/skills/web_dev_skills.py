import json
from collections.abc import Iterator

from src.runtime.config import get_runtime_settings
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext
from src.tools.web_dev_tools import WebDevTool


class WebDevSkill(BaseSkill):
    id = "web_dev"
    name = "Web Development Skill"
    description = (
        "Builds beautiful frontend websites using HTML, CSS, and JavaScript, "
        "and can deploy them on a server."
    )

    def __init__(self, model_client: OllamaModelClient, web_tool: WebDevTool) -> None:
        self._model_client = model_client
        self._web_tool = web_tool
        self._settings = get_runtime_settings()

    def execute(self, context: SkillContext) -> Iterator[dict]:
        messages = self._build_messages(context)

        yield {
            "type": "step_started",
            "step": "web_dev_analysis",
            "detail": "Analyzing user request for website generation.",
        }

        last_tool_result: str | None = None

        for iteration in range(self._settings.agent_max_turns):
            response = self._model_client.chat(
                messages=messages,
                tools=[self._web_tool.schema],
            )

            assistant_message = response.get("message", {})
            tool_calls = assistant_message.get("tool_calls") or []

            if not tool_calls:
                reply = assistant_message.get("content", "")

                yield {
                    "type": "step_completed",
                    "step": "web_dev_analysis",
                    "detail": "Generated frontend code and response.",
                }

                for token in self._chunk_text(reply):
                    yield {"type": "token", "content": token}

                yield {"type": "done"}
                return

            messages.append(assistant_message)

            for tool_call in tool_calls:
                function_call = tool_call.get("function", {})
                tool_name = function_call.get("name")
                arguments = function_call.get("arguments", {}) or {}

                if isinstance(arguments, str):
                    arguments = json.loads(arguments)

                command_action = arguments.get("action")

                yield {
                    "type": "tool_called",
                    "tool_name": tool_name,
                    "action": command_action,
                    "iteration": iteration + 1,
                }

                tool_event, tool_content = self._web_tool.execute(
                    server_id=context.server_id,
                    arguments=arguments,
                )

                last_tool_result = tool_content
                messages.append({"role": "tool", "content": tool_content})

                yield {
                    "type": "tool_event",
                    "tool_name": tool_event.tool_name,
                    "command": tool_event.command,
                    "exit_status": tool_event.exit_status,
                    "stdout": tool_event.stdout,
                    "stderr": tool_event.stderr,
                }

        fallback_reply = f"Last result:\n{last_tool_result}"

        yield {
            "type": "step_completed",
            "step": "web_dev_analysis",
            "detail": "Fallback response used.",
        }

        for token in self._chunk_text(fallback_reply):
            yield {"type": "token", "content": token}

        yield {"type": "done"}

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        for word in text.split(" "):
            yield word + " "

    @staticmethod
    def _build_messages(context: SkillContext) -> list[dict]:
        system_message = {
            "role": "system",
            "content": (
                "You are a web development assistant.\n"
                "When the user asks for a website:\n"
                "- Generate beautiful modern HTML, CSS, JS.\n"
                "- Use clean UI, gradients, animations, responsiveness.\n"
                "- After generating code, ask: 'Do you want me to run this in your browser?'\n"
                "- If user says YES → call tool with action=run_server.\n"
                "- If user says NO → stop.\n"
                "- When creating files → call tool with action=create_files.\n"
                "- Always ensure index.html links styles.css and script.js.\n"
                "- Do NOT install anything.\n"
                "- Do not show generated code for user , if user asked afterwords then only show the code"
                "- Prefer python3 http.server for hosting.\n"
                "- Default port: 5000.\n"
                "- as localhost will not execute try to find public ip address of particular server and bind to port"
                "eg if public ip adress of server is 3.6.36.5 then excute http://3.6.36.5:5000 ( this is just example to understand you ) "
                "Respond cleanly and professionally."
            ),
        }

        return [
            system_message,
            *context.history[-10:],
            {"role": "user", "content": context.user_message},
        ]