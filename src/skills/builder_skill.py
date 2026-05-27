import json
from collections.abc import Iterator

from src.runtime.ollama_client import OllamaModelClient
from src.skills.base import BaseSkill, SkillContext


class BuilderSkill(BaseSkill):
    id = "builder"
    name = "Builder"
    description = (
        "Creates beautiful static HTML, CSS, and JavaScript websites with a conversational, "
        "design-focused workflow."
    )

    def __init__(self, model_client: OllamaModelClient) -> None:
        self._model_client = model_client

    def execute(self, context: SkillContext) -> Iterator[dict]:
        if self._is_capability_question(context.user_message):
            yield {
                "type": "step_started",
                "step": "builder_conversation",
                "detail": "Answering the builder request conversationally.",
            }
            reply = self._build_conversational_reply(context)
            yield {
                "type": "step_completed",
                "step": "builder_conversation",
                "detail": "Shared builder guidance without generating files yet.",
            }
            for token in self._chunk_text(reply):
                yield {"type": "token", "content": token}
            yield {"type": "done"}
            return

        yield {
            "type": "step_started",
            "step": "builder_generate",
            "detail": "Designing a static website and generating the site files.",
        }

        result = self._generate_site(context)
        context.session_state["latest_builder_output"] = result

        yield {
            "type": "step_completed",
            "step": "builder_generate",
            "detail": "Generated the site files and summary.",
        }

        response = (
            f"{result['summary']}\n\n"
            "```html\n"
            f"{result['index_html']}\n"
            "```\n\n"
            "```css\n"
            f"{result['styles_css']}\n"
            "```\n\n"
            "```javascript\n"
            f"{result['script_js']}\n"
            "```"
        )
        for token in self._chunk_text(response):
            yield {"type": "token", "content": token}
        yield {"type": "done"}

    def _build_conversational_reply(self, context: SkillContext) -> str:
        prompt = (
            "You are ShellMate's Builder assistant.\n"
            "The user is asking about website building capabilities or approach, not asking for code generation yet.\n"
            "Respond warmly, clearly, and practically.\n"
            "Explain that you can create beautiful static HTML/CSS/JS websites, adapt to brand/style requests, "
            "and refine the design over follow-up prompts.\n"
            "Keep the answer concise and user-friendly."
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
            "Yes. I can design and generate static HTML, CSS, and JavaScript websites for you, "
            "including landing pages, portfolios, product pages, and other polished responsive layouts. "
            "If you describe the kind of website you want, I can generate the files and then refine them with you."
        )

    def _generate_site(self, context: SkillContext) -> dict[str, str]:
        prompt = (
            "You are ShellMate's Builder engine for static websites.\n"
            "Generate a beautiful, accurate, responsive static website from the user's request.\n"
            "Return JSON only with keys: summary, index_html, styles_css, script_js.\n"
            "Rules:\n"
            "- Build only static HTML, CSS, and vanilla JavaScript.\n"
            "- The HTML must link styles.css and script.js.\n"
            "- Make the design feel intentional, polished, and visually strong.\n"
            "- Avoid generic boilerplate layouts.\n"
            "- Keep the code clean and complete enough to run directly.\n"
            "- The summary should explain what was built in a friendly way.\n"
            "- Do not wrap the JSON in markdown fences.\n"
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
                "index_html": str(payload["index_html"]).strip(),
                "styles_css": str(payload["styles_css"]).strip(),
                "script_js": str(payload["script_js"]).strip(),
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return self._fallback_site(context.user_message)

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
    def _fallback_site(user_message: str) -> dict[str, str]:
        title = "Generated Website"
        return {
            "summary": (
                f"I created a first static website draft based on your request: \"{user_message}\". "
                "It includes a responsive landing-page structure with a polished visual style, "
                "and we can refine the layout, copy, colors, or sections in the next prompt."
            ),
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
                "      <p class=\"hero-copy\">This is a clean starter layout generated as a fallback draft.</p>\n"
                "      <a class=\"hero-action\" href=\"#details\">Explore</a>\n"
                "    </section>\n"
                "    <section class=\"details\" id=\"details\">\n"
                "      <article class=\"card\"><h2>Responsive</h2><p>Designed to adapt across screen sizes.</p></article>\n"
                "      <article class=\"card\"><h2>Stylish</h2><p>Uses layered backgrounds, spacing, and contrast.</p></article>\n"
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
                ".page-shell {\n"
                "  min-height: 100vh;\n"
                "  padding: 48px 20px;\n"
                "}\n"
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
                "@media (max-width: 640px) {\n"
                "  .hero { padding: 28px; }\n"
                "}\n"
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
