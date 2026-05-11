import re


MEETING_FIELD_WEIGHTS = {
    "meeting_name": 10,
    "responsible_unit": 5,
    "chairperson": 4,
    "recorder": 3,
    "attendees": 3,
    "location": 2,
}

ITEM_FIELD_WEIGHTS = {
    "content": 8,
    "owner": 5,
    "planned_date": 3,
    "actual_completed_date": 3,
    "tracking_result": 4,
}


def score_meeting(meeting, query):
    if not query:
        return 0, []

    lowered_query = query.lower()
    score = 0
    matched_fields = []

    for field, weight in MEETING_FIELD_WEIGHTS.items():
        value = meeting.get(field)
        if _matches(value, lowered_query):
            score += weight
            matched_fields.append(field)

    return score, matched_fields


def score_item(item, query):
    if not query:
        return 0, []

    lowered_query = query.lower()
    score = 0
    matched_fields = []

    for field, weight in ITEM_FIELD_WEIGHTS.items():
        value = item.get(field)
        if _matches(value, lowered_query):
            score += weight
            matched_fields.append(f"item_{field}")

    return score, matched_fields


def _matches(value, lowered_query):
    if value is None:
        return False
    if isinstance(value, list):
        return any(_matches(item, lowered_query) for item in value)
    haystack = str(value).lower()
    if _is_ascii_term(lowered_query):
        pattern = rf"(?<![a-z0-9]){re.escape(lowered_query)}(?![a-z0-9])"
        return re.search(pattern, haystack) is not None
    return lowered_query in haystack


def _is_ascii_term(query):
    return bool(query) and re.fullmatch(r"[a-z0-9 ._/-]+", query) is not None
