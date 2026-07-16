import re
from collections.abc import Iterator


def is_explicit_code_request(lowered: str) -> bool:
    return any(term in lowered for term in ("show code", "show me the code", "show html", "show css", "show javascript", "show js", "give me the code", "display the code", "view the code", "send the code"))


def is_explicit_generation_request(lowered: str) -> bool:
    return any(term in lowered for term in ("build me", "create me", "make me", "build a", "create a", "make a", "generate a", "design a", "landing page", "portfolio website", "homepage", "product page", "marketing page", "restaurant website", "static website", "html css js", "premium landing page"))


def is_vague_builder_request(lowered: str) -> bool:
    return lowered in ("i want to build a website", "i want a website", "build a website", "create a website", "make a website", "website")


def is_capability_request(lowered: str) -> bool:
    terms = ("what can you build", "what can you do", "can you build", "do you build", "can you create", "how do you build", "is it possible", "do you support", "website builder")
    return any(term in lowered for term in terms) or lowered.endswith("?")


def extract_folder_path(user_message: str) -> str | None:
    match = re.search(r"(?:path|folder path|directory)\s+(?:is\s+|at\s+)?([~/\.\w\-/]+)", user_message, re.IGNORECASE)
    return match.group(1).strip().rstrip(".,") if match else None


def extract_folder_name(user_message: str) -> str | None:
    match = re.search(r"(?:folder|directory)\s+(?:name\s+)?([a-zA-Z0-9_-]+)", user_message, re.IGNORECASE)
    return match.group(1).strip().lower() if match else None


def sanitize_slug(raw_slug: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw_slug.lower()).strip("-")
    return cleaned[:40] or "shellmate-site"


def is_generic_slug(slug: str) -> bool:
    return slug in {"website", "website-draft", "site", "draft", "shellmate-site", "generated-website", "website-template", "static-website"}


def clean_summary(summary: str, user_message: str) -> str:
    cleaned = summary.strip()
    prompt = user_message.strip().strip("\"'")
    for pattern in (re.escape(prompt), re.escape(f'"{prompt}"'), re.escape(f"'{prompt}'")):
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" :,-\n\t")
    return cleaned or "I built the first version of the website with a clear visual direction and a solid structure we can refine further."


def chunk_text(text: str) -> Iterator[str]:
    words = text.split(" ")
    for index, word in enumerate(words):
        yield word + (" " if index < len(words) - 1 else "")