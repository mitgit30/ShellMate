from dataclasses import dataclass

from src.memory.memory_manager import MemoryManager
from src.runtime.ollama_client import OllamaModelClient


NO_REPLY = "NO_REPLY"


@dataclass
class ExtractionResult:
    handoff: str
    session: str
    server_facts: dict[str, list[str]]


class ContextExtractor:
    def __init__(self, model_client: OllamaModelClient, memory_manager: MemoryManager) -> None:
        self._model_client = model_client
        self._memory_manager = memory_manager

    def extract(
        self,
        server_id: str,
        user_message: str,
        assistant_message: str,
        tool_outputs: list[str],
    ) -> str:
        extracted = self._run_extraction_turn(
            server_id=server_id,
            user_message=user_message,
            assistant_message=assistant_message,
            tool_outputs=tool_outputs,
        )
        if extracted == NO_REPLY:
            return NO_REPLY

        parsed = self._parse_markdown(extracted)
        if not parsed.handoff.strip():
            return NO_REPLY

        self._memory_manager.write_handoff(server_id, parsed.handoff)
        if parsed.server_facts:
            self._memory_manager.update_server_facts(server_id, parsed.server_facts)
        if parsed.session.strip():
            self._memory_manager.write_session(server_id, parsed.session)
        return extracted

    def _run_extraction_turn(
        self,
        server_id: str,
        user_message: str,
        assistant_message: str,
        tool_outputs: list[str],
    ) -> str:
        domain_instruction = (
            "You are ShellMate's silent context extractor.\n"
            "Your job is to extract only useful server and task facts from the completed turn.\n"
            "This turn is invisible to the user.\n"
            "Return NO_REPLY if nothing new or useful was discovered.\n"
            "Otherwise return markdown only in exactly this format:\n\n"
            "## Paths\n"
            "- bike-rentals: /home/ubuntu/shellmate-sites/bike-rentals\n\n"
            "## Packages\n"
            "- docker: 24.0.5\n\n"
            "## Ports\n"
            "- 3000: free\n\n"
            "## Containers\n"
            "- none running\n\n"
            "## Pending\n"
            "- user wants to build Docker image for bike-rentals\n\n"
            "Rules:\n"
            "- Prefer exact paths and exact package names when available.\n"
            "- Use tool outputs as the highest-confidence source.\n"
            "- Only include facts that were actually discovered in this turn.\n"
            "- Do not explain anything outside the markdown format.\n"
            "- If there is no meaningful new fact, return NO_REPLY only."
        )
        from src.runtime.prompt_composer import PromptComposer
        prompt = PromptComposer.compose_system_prompt(
            domain_instruction=domain_instruction,
            require_json=False,
        )
        known_handoff = self._memory_manager.read_handoff(server_id)
        known_facts = self._memory_manager.read_server_facts(server_id)
        known_session = self._memory_manager.read_session(server_id)
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"Existing handoff:\n{known_handoff or '<empty>'}\n\n"
                        f"Known server facts:\n{known_facts or '<empty>'}\n\n"
                        f"Current session:\n{known_session or '<empty>'}\n\n"
                        f"User message:\n{user_message}\n\n"
                        f"Assistant response:\n{assistant_message or '<empty>'}\n\n"
                        f"Tool outputs:\n{self._join_tool_outputs(tool_outputs)}"
                    ),
                },
            ],
            tools=[],
        )
        content = (response.get("message", {}).get("content", "") or "").strip()
        return content or NO_REPLY

    @staticmethod
    def _join_tool_outputs(tool_outputs: list[str]) -> str:
        cleaned = [item.strip() for item in tool_outputs if item and item.strip()]
        return "\n\n".join(cleaned) if cleaned else "<empty>"

    @staticmethod
    def _parse_markdown(content: str) -> ExtractionResult:
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for raw_line in content.splitlines():
            line = raw_line.rstrip()
            if line.startswith("## "):
                current = line[3:].strip()
                sections.setdefault(current, [])
                continue
            if current and line.strip():
                sections[current].append(line.strip())

        handoff_order = ("Paths", "Packages", "Ports", "Containers", "Pending")
        handoff_blocks: list[str] = []
        for section in handoff_order:
            lines = sections.get(section, [])
            if lines:
                handoff_blocks.append(f"## {section}\n" + "\n".join(lines))
        handoff = "\n\n".join(handoff_blocks)

        server_facts = {
            section: sections.get(section, [])
            for section in ("Paths", "Packages", "Ports", "Containers")
            if sections.get(section)
        }

        session_lines: list[str] = []
        pending_lines = sections.get("Pending", [])
        if pending_lines:
            session_lines.append("## Pending")
            session_lines.extend(pending_lines)
        path_lines = sections.get("Paths", [])
        if path_lines:
            if session_lines:
                session_lines.append("")
            session_lines.append("## Active Paths")
            session_lines.extend(path_lines)
        port_lines = sections.get("Ports", [])
        if port_lines:
            if session_lines:
                session_lines.append("")
            session_lines.append("## Active Ports")
            session_lines.extend(port_lines)

        session = "\n".join(session_lines).strip()
        return ExtractionResult(handoff=handoff, session=session, server_facts=server_facts)
