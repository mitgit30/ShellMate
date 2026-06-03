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
        if self._is_code_request(context.user_message):
            yield from self._show_latest_code(context)
            return

        if self._needs_discovery(context.user_message):
            yield from self._run_discovery(context)
            return

        if self._is_capability_question(context.user_message):
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

        result = self._generate_site(context)
        project_path = self._resolve_project_path(context.user_message, result["site_slug"])
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
            for token in self._chunk_text(
                "I designed the website, but I couldn't save the files on the server yet.\n\n"
                "If you want, I can help inspect the server-side issue next.\n\n"
                f"Technical details:\n{tool_output}"
            ):
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
        response = (
            f"{result['summary']}\n\n"
            f"I saved the website on the server at `{saved_path}`.\n"
            "The folder includes `index.html`, `styles.css`, and `script.js`.\n\n"
            "If you want, I can now refine the design, show you the code, or help you publish it."
        )
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
            reply = (
                "I don't have a generated website saved in this chat yet. "
                "Ask me to create one first, and then I can show you the code."
            )
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
        prompt = (
            "You are ShellMate's Builder assistant.\n"
            "The user is asking about website-building capability or approach, not asking you to generate code yet.\n"
            "Respond warmly, clearly, and like a product expert.\n"
            "Explain that you can create beautiful static HTML/CSS/JS websites, adapt to brand and style direction, "
            "save the generated files onto the connected server, and then refine the result in follow-up prompts.\n"
            "Keep the answer concise, natural, and user-friendly."
            + (f"\n\n{memory_block}" if memory_block else "")
        )
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                *context.history[-6:],
                {"role": "user", "content": context.user_message},
            ],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        return content.strip() or (
            "Yes. I can create static HTML, CSS, and JavaScript websites for you, "
            "shape the design around the style you want, save the files onto the connected server, "
            "and then keep refining the result with you."
        )

    def _build_discovery_reply(self, context: SkillContext) -> str:
        memory_block = self._memory_prompt_block(context)
        prompt = (
            "You are ShellMate's Builder assistant.\n"
            "The user has expressed a broad intent to build a website, but the request is still too vague to generate a good result.\n"
            "Do not generate code. Do not talk like an internal engine. Do not jump straight into implementation.\n"
            "Respond like a thoughtful creative collaborator.\n"
            "Briefly acknowledge the goal, then ask for the minimum high-value details needed to build a strong first version.\n"
            "Prefer a compact guided prompt, such as asking for:\n"
            "- website type or purpose\n"
            "- style or mood\n"
            "- main sections needed\n"
            "- optional brand name or target audience\n"
            "Keep it concise, natural, and friendly."
            + (f"\n\n{memory_block}" if memory_block else "")
        )
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                *context.history[-6:],
                {"role": "user", "content": context.user_message},
            ],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        return content.strip() or (
            "Absolutely. Before I design it, tell me a bit about what you want:\n\n"
            "1. What kind of website is it?\n"
            "2. What style should it have?\n"
            "3. What sections do you want on the page?\n\n"
            "If you want, you can answer in one line and I’ll build the first version from that."
        )

    def _generate_site(self, context: SkillContext) -> dict[str, str]:
        memory_block = self._memory_prompt_block(context)
        prompt = (
            "You are ShellMate's Builder engine for static websites.\n"
            "Generate a beautiful, accurate, responsive static website from the user's request.\n"
            "Return JSON only with keys: summary, site_slug, index_html, styles_css, script_js.\n"
            "Rules:\n"
            "- Build only static HTML, CSS, and vanilla JavaScript.\n"
            "- The HTML must link styles.css and script.js.\n"
            "- Make the design feel intentional, polished, and visually strong.\n"
            "- Avoid generic boilerplate layouts and generic business-site filler.\n"
            "- Infer a clear creative direction from the prompt.\n"
            "- Use a short, clean site_slug that fits the concept, not the full raw prompt.\n"
            "- The summary should describe what was built in a friendly way without dumping implementation details.\n"
            "- Do not wrap the JSON in markdown fences.\n"
            + (f"\n\n{memory_block}" if memory_block else "")
        )
        response = self._model_client.chat(
            messages=[
                {"role": "system", "content": prompt},
                *context.history[-6:],
                {"role": "user", "content": context.user_message},
            ],
            tools=[],
        )
        content = response.get("message", {}).get("content", "") or ""
        try:
            payload = json.loads(content)
            return {
                "summary": str(payload["summary"]).strip(),
                "site_slug": self._sanitize_slug(str(payload["site_slug"]).strip()),
                "index_html": str(payload["index_html"]).strip(),
                "styles_css": str(payload["styles_css"]).strip(),
                "script_js": str(payload["script_js"]).strip(),
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return self._fallback_site(context.user_message)

    @staticmethod
    def _needs_discovery(user_message: str) -> bool:
        lowered = user_message.lower().strip()
        vague_prompts = (
            "i want to build a website",
            "i want a website",
            "build a website",
            "create a website",
            "make a website",
            "website",
        )
        return lowered in vague_prompts

    @staticmethod
    def _is_capability_question(user_message: str) -> bool:
        lowered = user_message.lower()
        capability_terms = (
            "what can you build",
            "what can you do",
            "can you build",
            "do you build",
            "can you create",
            "how do you build",
            "is it possible",
            "do you support",
        )
        generation_terms = (
            "build me",
            "create a website",
            "make a website",
            "generate a website",
            "landing page",
            "portfolio website",
            "homepage",
            "html css js",
            "static website",
            "hero section",
        )
        if any(term in lowered for term in generation_terms):
            return False
        return any(term in lowered for term in capability_terms) or lowered.endswith("?")

    @staticmethod
    def _is_code_request(user_message: str) -> bool:
        lowered = user_message.lower()
        code_terms = (
            "show code",
            "show me the code",
            "show html",
            "show css",
            "show javascript",
            "show js",
            "give me the code",
            "display the code",
            "view the code",
        )
        return any(term in lowered for term in code_terms)

    def _resolve_project_path(self, user_message: str, generated_slug: str) -> str:
        explicit_path = self._extract_folder_path(user_message)
        if explicit_path:
            return explicit_path

        explicit_name = self._extract_folder_name(user_message)
        if explicit_name:
            return f"~/shellmate-sites/{explicit_name}"

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

    @staticmethod
    def _fallback_site(user_message: str) -> dict[str, str]:
        title = "Generated Website"
        return {
            "summary": (
                f"I created a first website draft based on your request: \"{user_message}\". "
                "It has a polished responsive layout and a strong visual foundation that we can refine together."
            ),
            "site_slug": "website-draft",
            "index_html": (
                "<!DOCTYPE html>\n"
                "<html lang=\"en\">\n"
                "<head>\n"
                "  <meta charset=\"UTF-8\" />\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
                f"  <title>{title}</title>\n"
                "  <link rel=\"stylesheet\" href=\"styles.css\" />\n"
                "</head>\n"
                "<body>\n"
                "  <main class=\"page-shell\">\n"
                "    <section class=\"hero\">\n"
                "      <p class=\"eyebrow\">ShellMate Builder</p>\n"
                "      <h1>Beautiful static site draft</h1>\n"
                "      <p class=\"hero-copy\">A refined starting point with a flexible structure for follow-up edits.</p>\n"
                "      <a class=\"hero-action\" href=\"#details\">Explore</a>\n"
                "    </section>\n"
                "    <section class=\"details\" id=\"details\">\n"
                "      <article class=\"card\"><h2>Responsive</h2><p>Built to adapt across desktop and mobile screens.</p></article>\n"
                "      <article class=\"card\"><h2>Polished</h2><p>Uses layered spacing, contrast, and visual rhythm.</p></article>\n"
                "      <article class=\"card\"><h2>Editable</h2><p>Ready for your next refinement prompt.</p></article>\n"
                "    </section>\n"
                "  </main>\n"
                "  <script src=\"script.js\"></script>\n"
                "</body>\n"
                "</html>"
            ),
            "styles_css": (
                ":root {\n"
                "  --bg: #f3efe7;\n"
                "  --ink: #1c1a18;\n"
                "  --accent: #b85c38;\n"
                "  --panel: rgba(255, 255, 255, 0.68);\n"
                "}\n"
                "* { box-sizing: border-box; }\n"
                "body {\n"
                "  margin: 0;\n"
                "  font-family: Georgia, 'Times New Roman', serif;\n"
                "  color: var(--ink);\n"
                "  background: radial-gradient(circle at top, #fff8ef, var(--bg));\n"
                "}\n"
                ".page-shell { min-height: 100vh; padding: 48px 20px; }\n"
                ".hero {\n"
                "  max-width: 960px;\n"
                "  margin: 0 auto 36px;\n"
                "  padding: 56px;\n"
                "  border-radius: 28px;\n"
                "  background: var(--panel);\n"
                "  backdrop-filter: blur(10px);\n"
                "  box-shadow: 0 18px 60px rgba(35, 26, 16, 0.12);\n"
                "}\n"
                ".eyebrow { text-transform: uppercase; letter-spacing: 0.18em; color: var(--accent); }\n"
                "h1 { font-size: clamp(2.6rem, 8vw, 5.6rem); line-height: 0.95; margin: 12px 0; }\n"
                ".hero-copy { max-width: 620px; font-size: 1.1rem; line-height: 1.7; }\n"
                ".hero-action {\n"
                "  display: inline-block;\n"
                "  margin-top: 18px;\n"
                "  padding: 14px 22px;\n"
                "  border-radius: 999px;\n"
                "  background: var(--ink);\n"
                "  color: white;\n"
                "  text-decoration: none;\n"
                "}\n"
                ".details {\n"
                "  max-width: 960px;\n"
                "  margin: 0 auto;\n"
                "  display: grid;\n"
                "  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));\n"
                "  gap: 18px;\n"
                "}\n"
                ".card {\n"
                "  padding: 24px;\n"
                "  border-radius: 22px;\n"
                "  background: rgba(255, 255, 255, 0.9);\n"
                "  box-shadow: 0 12px 32px rgba(35, 26, 16, 0.08);\n"
                "}\n"
                "@media (max-width: 640px) { .hero { padding: 28px; } }\n"
            ),
            "script_js": (
                "document.querySelectorAll('a[href^=\"#\"]').forEach((link) => {\n"
                "  link.addEventListener('click', (event) => {\n"
                "    const target = document.querySelector(link.getAttribute('href'));\n"
                "    if (!target) return;\n"
                "    event.preventDefault();\n"
                "    target.scrollIntoView({ behavior: 'smooth', block: 'start' });\n"
                "  });\n"
                "});"
            ),
        }

    @staticmethod
    def _chunk_text(text: str) -> Iterator[str]:
        words = text.split(" ")
        for index, word in enumerate(words):
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix
