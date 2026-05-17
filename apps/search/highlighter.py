from __future__ import annotations

import re

from .ranking import is_ascii_term


HIGHLIGHT_FIELDS = ("meeting_name", "content", "owner", "responsible_unit", "tracking_result")


def collect_matched_snippets(query: str, meeting: dict, items: list[dict]) -> list[dict]:
    if not query:
        return []

    snippets = []
    seen = set()

    for field in ("meeting_name", "responsible_unit"):
        snippet = make_highlight_snippet(field, meeting.get(field), query)
        if snippet and (field, snippet) not in seen:
            seen.add((field, snippet))
            snippets.append({"field": field, "snippet": snippet})

    for item in items:
        for field in ("content", "owner", "tracking_result"):
            snippet = make_highlight_snippet(field, item.get(field), query)
            if snippet and (field, snippet) not in seen:
                seen.add((field, snippet))
                snippets.append({"field": field, "snippet": snippet})

    return snippets[:8]


def make_highlight_snippet(field: str, value, query: str) -> str | None:
    if field not in HIGHLIGHT_FIELDS or value is None:
        return None

    text = str(value)
    if not text.strip():
        return None

    match = find_match(text, query)
    if not match:
        return None

    start, end = match.span()
    if len(text) <= 80:
        return apply_highlight(text, query)

    left = max(0, start - 20)
    right = min(len(text), end + 30)
    snippet = text[left:right]
    snippet = apply_highlight(snippet, query)
    if left > 0:
        snippet = f"...{snippet}"
    if right < len(text):
        snippet = f"{snippet}..."
    return snippet


def apply_highlight(text: str, query: str) -> str:
    match = find_match(text, query)
    if not match:
        return text
    start, end = match.span()
    return f"{text[:start]}<mark>{text[start:end]}</mark>{text[end:]}"


def find_match(text: str, query: str):
    if not query:
        return None
    if is_ascii_term(query.lower()):
        pattern = re.compile(rf"(?i)(?<![a-z0-9]){re.escape(query)}(?![a-z0-9])")
        return pattern.search(text)
    return re.search(re.escape(query), text, flags=re.IGNORECASE)
