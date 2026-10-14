import re
from difflib import SequenceMatcher
from collections.abc import Iterator


def is_explicit_code_request(lowered: str) -> bool:
    return any(term in lowered for term in ("show code", "show me the code", "show html", "show css", "show javascript", "show js", "give me the code", "display the code", "view the code", "send the code"))


def is_explicit_generation_request(lowered: str) -> bool:
    action = r"(?:build|create|make|generate|design)"
    subject = r"(?:website|web\s?page|site|landing\s?page|portfolio|homepage|product\s?page|marketing\s?page)"
    return bool(re.search(rf"\b{action}\b.*\b{subject}\b", lowered))


def is_vague_builder_request(lowered: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", lowered)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    words = normalized.split()
    if not re.search(r"\b(?:website|web\s+page|site|landing\s+page)\b", normalized):
        return False

    # Ignore conversational framing and common article typos (e.g. "abn website")
    # so a greeting or typo cannot turn a generic ask into an executable brief.
    framing = {
        "hey", "hi", "hello", "please", "can", "could", "would", "you", "i",
        "want", "need", "like", "to", "build", "create", "make", "generate",
        "design", "me", "a", "an", "the", "for", "website", "web", "page",
        "site", "landing", "is", "it", "possible",
    }
    meaningful_words = [
        word for word in words
        if word not in framing
        and max(SequenceMatcher(None, word, article).ratio() for article in ("a", "an", "the")) < 0.8
    ]
    return not meaningful_words


def has_builder_details(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    words = re.sub(r"\s+", " ", normalized).strip().split()
    non_details = {
        "hey", "hi", "hello", "yes", "yeah", "yep", "sure", "okay", "ok",
        "please", "can", "could", "would", "you", "i", "we", "want", "need",
        "like", "to", "build", "create", "make", "generate", "design", "me",
        "my", "a", "an", "the", "for", "website", "web", "page", "site",
        "landing", "it", "is", "its", "this", "that", "one", "something",
    }
    return any(
        word not in non_details
        and max(SequenceMatcher(None, word, article).ratio() for article in ("a", "an", "the")) < 0.8
        for word in words
    )


def is_capability_request(lowered: str) -> bool:
    terms = (
        "what can you build",
        "what can you do",
        "do you build websites",
        "can you build websites",
        "can you create websites",
        "how do you build",
        "is it possible to build a website",
        "do you support website",
        "website builder",
    )
    if any(term in lowered for term in terms):
        return True
    return bool(
        re.fullmatch(
            r"(?:can|could|would) you (?:also )?(?:build|create|make) (?:websites|sites|landing pages)\??",
            lowered.strip(),
        )
    )


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
