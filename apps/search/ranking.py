from __future__ import annotations

import re
from datetime import date, datetime

from django.utils import timezone

from apps.item_status import BLANK_VALUES, is_meaningful_value, item_status_payload


MEETING_KEYWORD_WEIGHTS = {
    "meeting_name": 10,
    "responsible_unit": 5,
    "chairperson": 4,
    "recorder": 3,
    "attendees": 3,
    "location": 2,
}

ITEM_KEYWORD_WEIGHTS = {
    "content": 8,
    "owner": 5,
    "planned_date": 3,
    "actual_completed_date": 3,
    "tracking_result": 4,
}

STRUCTURE_WEIGHTS = {
    "meeting_name": 5,
    "content": 4,
    "owner": 3,
    "responsible_unit": 3,
    "attendees": 2,
}

BLANK_OWNER_VALUES = BLANK_VALUES
TASK_INTENT_TERMS = {
    "owner",
    "responsible",
    "assignee",
    "person in charge",
    "due",
    "deadline",
    "planned",
    "completed",
    "completion",
    "unfinished",
    "pending",
    "overdue",
    "tracking",
    "follow-up",
    "follow up",
    "負責",
    "負責人",
    "權責",
    "預計",
    "日期",
    "期限",
    "完成",
    "完成日",
    "實際完成",
    "未完成",
    "逾期",
    "追蹤",
    "結果",
    "待辦",
    "任務",
}


def score_meeting_metadata(meeting: dict, query: str) -> dict:
    matched_fields = []
    keyword_score = 0.0
    structure_score = 0.0

    if query:
        lowered_query = query.lower()
        for field, weight in MEETING_KEYWORD_WEIGHTS.items():
            value = meeting.get(field)
            if matches_query(value, lowered_query):
                matched_fields.append(field)
                keyword_score += weight
                structure_score += STRUCTURE_WEIGHTS.get(field, 0)

    return {
        "keyword_score": float(keyword_score),
        "structure_score": float(structure_score),
        "matched_fields": matched_fields,
    }


def score_item(item: dict, query: str) -> dict:
    matched_fields = []
    keyword_score = 0.0
    structure_score = 0.0

    if query:
        lowered_query = query.lower()
        for field, weight in ITEM_KEYWORD_WEIGHTS.items():
            value = item.get(field)
            if matches_query(value, lowered_query):
                field_name = f"item_{field}" if field != "content" else "item_content"
                matched_fields.append(field_name)
                keyword_score += weight
                structure_score += STRUCTURE_WEIGHTS.get(field, 0)

    task_score = score_task(item, query)

    return {
        "keyword_score": float(keyword_score),
        "structure_score": float(structure_score),
        "task_score": float(task_score),
        "matched_fields": matched_fields,
    }


def score_task(item: dict, query: str = "") -> float:
    if not has_task_intent(query):
        return 0.0

    score = 0.0
    if has_owner_value(item.get("owner")):
        score += 2
    if has_value(item.get("planned_date")):
        score += 2
    if item_status_payload(item)["status"] != "completed":
        score += 2
    if not has_value(item.get("tracking_result")):
        score += 1
    return score


def has_task_intent(query: str | None) -> bool:
    normalized_query = str(query or "").strip().lower()
    if not normalized_query:
        return False
    return any(term in normalized_query for term in TASK_INTENT_TERMS)


def score_recency(meeting_date_value: str | None, now: date | None = None) -> float:
    parsed_date = parse_iso_date(meeting_date_value)
    if not parsed_date:
        return 0.0

    today = now or timezone.localdate()
    age_days = (today - parsed_date).days
    if age_days < 0:
        age_days = 0

    if age_days <= 30:
        return 5.0
    if age_days <= 90:
        return 3.0
    if age_days <= 180:
        return 1.0
    return 0.0


def finalize_item_score(score_detail: dict) -> float:
    return float(
        score_detail.get("keyword_score", 0)
        + score_detail.get("structure_score", 0)
        + score_detail.get("task_score", 0)
        + score_detail.get("feedback_score", 0)
        + score_detail.get("graph_score", 0)
    )


def finalize_meeting_score(score_detail: dict) -> float:
    return float(
        score_detail.get("keyword_score", 0)
        + score_detail.get("structure_score", 0)
        + score_detail.get("task_score", 0)
        + score_detail.get("recency_score", 0)
        + score_detail.get("feedback_score", 0)
        + score_detail.get("graph_score", 0)
    )


def matches_query(value, lowered_query: str) -> bool:
    if not lowered_query:
        return False
    if value is None:
        return False
    if isinstance(value, list):
        return any(matches_query(item, lowered_query) for item in value)

    haystack = str(value).lower()
    if is_ascii_term(lowered_query):
        pattern = rf"(?<![a-z0-9]){re.escape(lowered_query)}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return lowered_query in haystack


def is_ascii_term(query: str) -> bool:
    return bool(query) and re.fullmatch(r"[a-z0-9 ._/-]+", query) is not None


def has_owner_value(value) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if not text:
        return False
    return text.lower() not in BLANK_OWNER_VALUES


def has_value(value) -> bool:
    return is_meaningful_value(value)


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
