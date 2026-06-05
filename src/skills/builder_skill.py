import json
import re
from collections.abc import Iterator

from src.memory.memory_manager import MemoryManager
from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext
from src.tools.builder_tool import BuilderTool


class BuilderSkill(BaseSkill):
    id = "builder"
    name = "Builder"
    description = (
        "Designs and generates beautiful static HTML, CSS, and JavaScript websites "
        "through a conversational design workflow."
    )

    def __init__(self, model_client: OllamaModelClient, builder_tool: BuilderTool, memory_manager: MemoryManager) -> None:
        super().__init__(memory_manager=memory_manager)
        self._model_client = model_client
        self._builder_tool = builder_tool

    def execute(self, context: SkillContext) -> Iterator[dict]:
        intent = self._detect_builder_intent(context)

        if intent == "show_code":
            yield from self._show_latest_code(context)
            return

        if intent == "discovery":
            yield from self._run_discovery(context)
            return

        if intent == "capability":
            yield from self._answer_capability_question(context)
            return

        yield from self._generate_and_save_site(context)

    def _answer_capability_question(self, context: SkillContext) -> Iterator[dict]:
        yield {
            "type": "step_started",
            "step": "builder_conversation",
            "detail": "Answering the builder request conversationally.",
        }
        reply = self._build_capability_reply(context)
        yield {
            "type": "step_completed",
            "step": "builder_conversation",
            "detail": "Shared builder guidance without generating files.",
        }
        for token in self._chunk_text(reply):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _run_discovery(self, context: SkillContext) -> Iterator[dict]:
        yield {
            "type": "step_started",
            "step": "builder_discovery",
            "detail": "Collecting design direction before generating the website.",
        }
        reply = self._build_discovery_reply(context)
        yield {
            "type": "step_completed",
            "step": "builder_discovery",
            "detail": "Asked for design details before generation.",
        }
        for token in self._chunk_text(reply):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _generate_and_save_site(self, context: SkillContext) -> Iterator[dict]:
        yield {
            "type": "step_started",
            "step": "builder_generate",
            "detail": "Designing the website and preparing the site files.",
        }

        request_details = self._extract_build_request(context)
        try:
            result = self._generate_site(context, request_details)
        except ValueError:
            yield {
                "type": "step_completed",
                "step": "builder_generate",
                "detail": "Builder could not generate a reliable website payload from the request.",
            }
            for token in self._chunk_text(self._render_generation_retry(context, request_details)):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return
        project_path = self._resolve_project_path(request_details, result["site_slug"])
        files = {
            "index.html": result["index_html"],
            "styles.css": result["styles_css"],
            "script.js": result["script_js"],
        }

        tool_event, tool_output = self._builder_tool.write_static_site(
            server_id=context.server_id,
            project_path=project_path,
            files=files,
        )
        yield {
            "type": "tool_called",
            "tool_name": "builder_write_site",
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
                "step": "builder_generate",
                "detail": "Site generation finished, but writing files to the server failed.",
            }
            for token in self._chunk_text(self._render_write_failure(context, tool_output)):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        saved_path = self._builder_tool.extract_saved_path(tool_event.stdout) or project_path
        context.session_state["latest_builder_output"] = {
            **result,
            "project_path": saved_path,
        }

        yield {
            "type": "step_completed",
            "step": "builder_generate",
            "detail": "Generated the site files and saved them on the server.",
        }
        response = self._render_generation_success(context, result, saved_path)
        for token in self._chunk_text(response):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _show_latest_code(self, context: SkillContext) -> Iterator[dict]:
        yield {
            "type": "step_started",
            "step": "builder_show_code",
            "detail": "Sharing the latest generated site code.",
        }
        latest = context.session_state.get("latest_builder_output")
        if not latest:
            reply = self._render_no_code_available(context)
        else:
            project_path = latest.get("project_path", "<unknown path>")
            reply = (
                f"Here is the latest website code for `{project_path}`.\n\n"
                "```html\n"
                f"{latest['index_html']}\n"
                "```\n\n"
                "```css\n"
                f"{latest['styles_css']}\n"
                "```\n\n"
                "```javascript\n"
                f"{latest['script_js']}\n"
                "```"
            )
        yield {
            "type": "step_completed",
            "step": "builder_show_code",
            "detail": "Returned the saved builder code on request.",
        }
        for token in self._chunk_text(reply):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _build_capability_reply(self, context: SkillContext) -> str:
        memory_block = self._memory_prompt_block(context)
        return self._generate_text(
            instruction=(
                "The user is asking about Builder capability or approach, not asking you to generate code yet. "
                "Respond warmly, clearly, and like a product expert. "
                "Explain that you can create beautiful static HTML/CSS/JS websites, adapt to brand and style direction, "
                "save the generated files onto the connected server, and refine the result in follow-up prompts."
            ),
            context=context,
            fallback=(
                "Yes. I can create static HTML, CSS, and JavaScript websites for you, "
                "shape the design around the style you want, save the files onto the connected server, "
                "and then keep refining the result with you."
            ),
            extra={"memory_block": memory_block},
        )

    def _build_discovery_reply(self, context: SkillContext) -> str:
        memory_block = self._memory_prompt_block(context)
        return self._generate_text(
            instruction=(
                "The user wants to build a website, but the request is still too vague to generate a strong result. "
                "Do not generate code. Respond like a thoughtful creative collaborator. "
                "Ask for the minimum high-value details needed to build a strong first version, such as website type, style, sections, brand name, or audience."
            ),
            context=context,
            fallback=(
                "Absolutely. Before I design it, tell me a bit about what you want:\n\n"
                "1. What kind of website is it?\n"
                "2. What style should it have?\n"
                "3. What sections do you want on the page?\n\n"
                "If you want, you can answer in one line and I’ll build the first version from that."
            ),
            extra={"memory_block": memory_block},
        )

    def _generate_site(self, context: SkillContext, request_details: dict[str, object]) -> dict[str, str]:
        memory_block = self._memory_prompt_block(context)
        prompt = (
            "You are the Builder engine inside ShellMate — a product that turns natural language into beautiful, shippable static websites.\n"
            "Your output is a JSON object with exactly these keys: summary, site_slug, index_html, styles_css, script_js.\n"
            "\n"
            "## What you're building\n"
            "A complete static site: real HTML structure, a dedicated stylesheet, and vanilla JS where it adds value.\n"
            "The HTML must link styles.css via <link> and script.js via <script>.\n"
            "Build only static files — no frameworks, no build tools, no server-side logic.\n"
            "\n"
            "## Design standard\n"
            "Every site must feel like it was designed by someone with taste, not generated by a machine.\n"
            "Before writing a single line of code, commit to a clear creative direction: editorial, brutalist, luxury, playful, editorial-dark, organic, retro-tech — pick one and execute it with precision.\n"
            "Use distinctive typography (Google Fonts or system stacks with character). Avoid Inter, Roboto, and Arial.\n"
            "Use a cohesive color system with CSS variables. Dominant palette + one sharp accent. No purple gradients on white.\n"
            "Add motion that serves the mood: a staggered load-in, a scroll reveal, a hover state that surprises.\n"
            "Layouts should feel considered — asymmetry, generous spacing, visual hierarchy that guides the eye.\n"
            "Never produce generic hero → features → CTA boilerplate. Every page structure should match the concept.\n"
            "\n"
            "## Output rules\n"
            "- site_slug: short, lowercase, hyphenated. Derived from the actual concept or brand — never 'site', 'draft', 'website', 'generated-website', or 'shellmate-site'.\n"
            "- summary: 1–3 sentences. Describe what was built in plain, friendly language. Write it like a product handoff note to the user — not a prompt echo, not a feature list, not implementation detail.\n"
            "- Return raw JSON only. No markdown fences, no preamble, no commentary outside the JSON.\n"
            "\n"
            "## Quality bar\n"
            "The final result should feel like something a designer and a developer shipped together — not like AI filler.\n"
            "If the request is vague, infer the strongest possible creative direction and build that. Do not default to safe.\n"
            + (f"\n\n{memory_block}" if memory_block else "")
        )
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                *context.history[-6:],
                {"role": "user", "content": context.user_message},
                {"role": "system", "content": json.dumps(request_details, ensure_ascii=True)},
            ],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        try:
            payload = json.loads(content)
            slug = self._finalize_site_slug(
                raw_slug=str(payload["site_slug"]).strip(),
                request_details=request_details,
                user_message=context.user_message,
            )
            return {
                "summary": self._clean_summary(str(payload["summary"]).strip(), context.user_message),
                "site_slug": slug,
                "index_html": str(payload["index_html"]).strip(),
                "styles_css": str(payload["styles_css"]).strip(),
                "script_js": str(payload["script_js"]).strip(),
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise ValueError("Builder generation did not return a valid structured website payload.")

    def _detect_builder_intent(self, context: SkillContext) -> str:
        payload = self._generate_json(
            instruction=(
                "Classify the user's builder request. "
                "Return JSON only with key intent. "
                "Valid values: show_code, discovery, capability, generate. "
                "Use discovery when the user wants a website but has not given enough design direction yet. "
                "Use capability when the user is asking what Builder can do. "
                "Use show_code when the user explicitly wants to see the code. "
                "Otherwise use generate."
            ),
            context=context,
            extra={"latest_builder_output": context.session_state.get("latest_builder_output", {})},
        )
        intent = str(payload.get("intent", "generate")).strip().lower()
        if intent in {"show_code", "discovery", "capability", "generate"}:
            return intent
        return "generate"

    def _extract_build_request(self, context: SkillContext) -> dict[str, object]:
        payload = self._generate_json(
            instruction=(
                "Extract the structured builder request from the full conversation context. "
                "Return JSON only with keys: website_type, style_direction, sections, target_audience, brand_name, project_path, folder_name. "
                "Use null for unknown scalar fields and [] for unknown sections. "
                "If the user clearly specified a save path or folder name, include it."
            ),
            context=context,
            extra={"latest_builder_output": context.session_state.get("latest_builder_output", {})},
        )
        normalized: dict[str, object] = {}
        for key in ("website_type", "style_direction", "target_audience", "brand_name", "project_path", "folder_name"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                normalized[key] = value.strip().rstrip(".,")
        sections = payload.get("sections")
        if isinstance(sections, list):
            normalized["sections"] = [str(item).strip() for item in sections if str(item).strip()]
        return normalized

    def _resolve_project_path(self, request_details: dict[str, object], generated_slug: str) -> str:
        explicit_path = request_details.get("project_path")
        if isinstance(explicit_path, str) and explicit_path.strip():
            return explicit_path.strip()

        folder_name = request_details.get("folder_name")
        if isinstance(folder_name, str) and folder_name.strip():
            return f"~/shellmate-sites/{self._sanitize_slug(folder_name)}"

        return f"~/shellmate-sites/{generated_slug}"

    @staticmethod
    def _extract_folder_path(user_message: str) -> str | None:
        match = re.search(
            r"(?:path|folder path|directory)\s+(?:is\s+|at\s+)?([~/.\w\-/]+)",
            user_message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().rstrip(".,")
        return None

    @staticmethod
    def _extract_folder_name(user_message: str) -> str | None:
        match = re.search(
            r"(?:folder|directory)\s+(?:name\s+)?([a-zA-Z0-9_-]+)",
            user_message,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).strip().lower()
        return None

    @staticmethod
    def _sanitize_slug(raw_slug: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", raw_slug.lower()).strip("-")
        return cleaned[:40] or "shellmate-site"

    def _finalize_site_slug(self, raw_slug: str, request_details: dict[str, object], user_message: str) -> str:
        sanitized = self._sanitize_slug(raw_slug)
        if self._is_generic_slug(sanitized):
            derived = self._derive_slug_from_request(request_details, user_message)
            if derived:
                return derived
        return sanitized

    @staticmethod
    def _is_generic_slug(slug: str) -> bool:
        generic = {
            "website",
            "website-draft",
            "site",
            "draft",
            "shellmate-site",
            "generated-website",
            "website-template",
            "static-website",
        }
        return slug in generic

    def _derive_slug_from_request(self, request_details: dict[str, object], user_message: str) -> str:
        candidates: list[str] = []
        for key in ("brand_name", "website_type", "target_audience", "folder_name"):
            value = request_details.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
        sections = request_details.get("sections")
        if isinstance(sections, list) and sections:
            first = str(sections[0]).strip()
            if first:
                candidates.append(first)
        if not candidates and user_message.strip():
            candidates.append(user_message.strip())

        for candidate in candidates:
            slug = self._sanitize_slug(candidate)
            if slug and not self._is_generic_slug(slug):
                return slug
        return "shellmate-site"

    @staticmethod
    def _clean_summary(summary: str, user_message: str) -> str:
        cleaned = summary.strip()
        prompt = user_message.strip().strip("\"'")
        patterns = [
            re.escape(prompt),
            re.escape(f"\"{prompt}\""),
            re.escape(f"'{prompt}'"),
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" :,-\n\t")
        if not cleaned:
            return "I built the first version of the website with a clear visual direction and a solid structure we can refine further."
        return cleaned

    def _render_write_failure(self, context: SkillContext, tool_output: str) -> str:
        return self._generate_text(
            instruction=(
                "The website was generated, but saving the files to the server failed. "
                "Explain that clearly, reassure the user the design work is ready, and offer to inspect the server-side issue next."
            ),
            context=context,
            fallback=(
                "I designed the website, but I couldn't save the files on the server yet.\n\n"
                "If you want, I can help inspect the server-side issue next.\n\n"
                f"Technical details:\n{tool_output}"
            ),
            extra={"tool_output": tool_output},
        )

    def _render_generation_success(self, context: SkillContext, result: dict[str, str], saved_path: str) -> str:
        return self._generate_text(
            instruction=(
                "Summarize the generated website in a natural, user-friendly way. "
                "Mention where it was saved on the server, mention the files created, "
                "and offer the next helpful actions such as refine, show code, or publish."
            ),
            context=context,
            fallback=(
                f"{result['summary']}\n\n"
                f"I saved the website on the server at `{saved_path}`.\n"
                "The folder includes `index.html`, `styles.css`, and `script.js`.\n\n"
                "If you want, I can now refine the design, show you the code, or help you publish it."
            ),
            extra={"builder_result": result, "saved_path": saved_path},
        )

    def _render_no_code_available(self, context: SkillContext) -> str:
        return self._generate_text(
            instruction=(
                "Tell the user there is no generated website saved in this chat yet, "
                "and ask them to create one first before requesting code."
            ),
            context=context,
            fallback=(
                "I don't have a generated website saved in this chat yet. "
                "Ask me to create one first, and then I can show you the code."
            ),
        )

    def _render_generation_retry(self, context: SkillContext, request_details: dict[str, object]) -> str:
        return self._generate_text(
            instruction=(
                "The builder could not generate a reliable website from the current request. "
                "Do not invent a generic site. Ask the user for a bit more concrete design direction so you can build the right thing."
            ),
            context=context,
            fallback=(
                "I’m not confident enough to generate the right website from the current request yet.\n\n"
                "Give me a little more direction, like the website type, visual style, and main sections you want, and I’ll build a proper first version."
            ),
            extra={"request_details": request_details},
        )

    def _generate_json(self, instruction: str, context: SkillContext, extra: dict | None = None) -> dict:
        memory_block = self._memory_prompt_block(context)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's Builder assistant.\n"
                    f"{instruction}\n"
                    "Return valid JSON only."
                    + (f"\n\n{memory_block}" if memory_block else "")
                ),
            },
            *context.history[-8:],
            {"role": "user", "content": context.user_message},
        ]
        if extra:
            messages.append({"role": "system", "content": json.dumps(extra, ensure_ascii=True)})
        response = self._model_client.chat(messages=messages, tools=[])
        content = response.get("message", {}).get("content", "") or "{}"
        try:
            payload = json.loads(content)
            return payload if isinstance(payload, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}

    def _generate_text(
        self,
        instruction: str,
        context: SkillContext,
        fallback: str,
        extra: dict | None = None,
    ) -> str:
        memory_block = self._memory_prompt_block(context)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are ShellMate's Builder assistant.\n"
                    f"{instruction}\n"
                    "Respond naturally, clearly, and briefly."
                    + (f"\n\n{memory_block}" if memory_block else "")
                ),
            },
            *context.history[-6:],
            {"role": "user", "content": context.user_message},
        ]
        if extra:
            messages.append({"role": "system", "content": json.dumps(extra, ensure_ascii=True)})
        response = self._model_client.chat(messages=messages, tools=[])
        content = (response.get("message", {}).get("content", "") or "").strip()
        return content or fallback

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix
