from typing import Any


class PromptComposer:
    @staticmethod
    def build_memory_block(
        server_id: str,
        memory_manager: Any,
        historical_query: str | None = None,
    ) -> str:
        """Fetch and format the memory block consistently."""
        handoff = memory_manager.read_handoff(server_id)
        server_facts = memory_manager.read_server_facts(server_id)
        session = memory_manager.read_session(server_id)

        blocks: list[str] = []
        if handoff:
            blocks.append(f"--- HANDOFF FROM PREVIOUS SKILL ---\n{handoff}")
        if server_facts:
            blocks.append(f"--- KNOWN SERVER FACTS ---\n{server_facts}")
        if session:
            blocks.append(f"--- CURRENT SESSION CONTEXT ---\n{session}")
        if historical_query and PromptComposer._is_historical_query(historical_query):
            historical = memory_manager.search_historical_memory(
                server_id=server_id,
                query=historical_query,
                limit=3,
            )
            if historical:
                blocks.append(
                    "--- RELEVANT HISTORICAL SERVER CONTEXT ---\n"
                    + "\n\n".join(f"- {item}" for item in historical)
                )
        return "\n\n".join(blocks)

    @staticmethod
    def compose_system_prompt(
        domain_instruction: str,
        server_id: str | None = None,
        memory_manager: Any = None,
        require_json: bool = False,
        historical_query: str | None = None,
    ) -> str:
        """Combines the domain instruction with centralized formatting, safety rules, and memory."""
        parts = [domain_instruction.strip()]

        if require_json:
            parts.append(
                "Return raw, valid JSON only. Do not wrap in markdown code blocks or code fences. "
                "Do not include preamble, summary, or commentary outside the JSON body."
            )
        else:
            parts.append(
                "Respond naturally, clearly, and briefly. Do not mention internal routing, "
                "skills, tool executions, or internal pipeline mechanics unless asked."
            )

        if server_id and memory_manager:
            memory_block = PromptComposer.build_memory_block(
                server_id,
                memory_manager,
                historical_query=historical_query,
            )
            if memory_block:
                parts.append(memory_block)

        return "\n\n".join(parts)

    @staticmethod
    def _is_historical_query(query: str) -> bool:
        lowered = query.lower()
        terms = (
            "previous",
            "previously",
            "earlier",
            "last time",
            "before",
            "history",
            "historical",
            "old deployment",
            "old error",
            "what happened",
            "did we",
            "have we",
            "again",
        )
        return any(term in lowered for term in terms)
