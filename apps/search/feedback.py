from __future__ import annotations

from collections import Counter

from .mongo import get_search_click_logs_collection


def build_feedback_context(query: str | None) -> dict:
    click_logs = list(get_search_click_logs_collection().find({}, {"_id": 0}))
    normalized_query = normalize_feedback_query(query or "")

    meeting_click_counts = Counter()
    item_click_counts = Counter()
    similar_meeting_click_counts = Counter()
    similar_item_click_counts = Counter()

    for log in click_logs:
        meeting_id = log.get("meeting_id")
        item_id = log.get("item_id")
        if meeting_id:
            meeting_click_counts[meeting_id] += 1
        if item_id:
            item_click_counts[item_id] += 1

        if not normalized_query:
            continue

        historical_query = normalize_feedback_query(log.get("query", ""))
        if are_similar_queries(normalized_query, historical_query):
            if meeting_id:
                similar_meeting_click_counts[meeting_id] += 1
            if item_id:
                similar_item_click_counts[item_id] += 1

    return {
        "meeting_click_counts": meeting_click_counts,
        "item_click_counts": item_click_counts,
        "similar_meeting_click_counts": similar_meeting_click_counts,
        "similar_item_click_counts": similar_item_click_counts,
    }


def score_meeting_feedback(meeting_id: str | None, context: dict) -> float:
    if not meeting_id:
        return 0.0
    global_clicks = context["meeting_click_counts"].get(meeting_id, 0)
    similar_clicks = context["similar_meeting_click_counts"].get(meeting_id, 0)
    return float(global_clicks * 0.5 + similar_clicks * 0.5)


def score_item_feedback(item_id: str | None, context: dict) -> float:
    if not item_id:
        return 0.0
    global_clicks = context["item_click_counts"].get(item_id, 0)
    similar_clicks = context["similar_item_click_counts"].get(item_id, 0)
    return float(global_clicks * 1.0 + similar_clicks * 0.5)


def normalize_feedback_query(query: str) -> str:
    return " ".join(part for part in str(query).strip().lower().split() if part)


def are_similar_queries(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left in right or right in left:
        return True

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return False

    overlap = len(left_tokens & right_tokens)
    ratio = overlap / max(len(left_tokens), len(right_tokens))
    return ratio >= 0.5
