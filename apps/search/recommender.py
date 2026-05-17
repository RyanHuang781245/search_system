from __future__ import annotations

import re
from collections import Counter

from apps.meetings.services import _serialize_mongo_document

from .mongo import get_meeting_items_collection, get_meeting_minutes_collection


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*|[\u4e00-\u9fff]{2,}")
STOPWORDS = {
    "meeting",
    "minutes",
    "record",
    "會議",
    "記錄",
    "項目",
    "內容",
}


def find_related_meetings(meeting_id: str, limit: int = 10) -> dict | None:
    minutes_collection = get_meeting_minutes_collection()
    items_collection = get_meeting_items_collection()

    target_meeting = minutes_collection.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not target_meeting:
        return None

    all_meetings = [doc for doc in minutes_collection.find({}, {"_id": 0}) if doc.get("meeting_id") != meeting_id]
    target_items = list(items_collection.find({"meeting_id": meeting_id}, {"_id": 0}))

    target_attendees = set(_normalized_people(target_meeting.get("attendees")))
    target_owners = {item.get("owner") for item in target_items if _has_text(item.get("owner"))}
    target_keywords = _extract_keywords(target_meeting.get("meeting_name"))
    target_keywords.update(_extract_keywords(" ".join(item.get("content", "") for item in target_items)))

    related_results = []
    for candidate in all_meetings:
        reasons = []
        score = 0.0
        candidate_items = list(items_collection.find({"meeting_id": candidate.get("meeting_id")}, {"_id": 0}))

        if target_meeting.get("responsible_unit") and target_meeting.get("responsible_unit") == candidate.get("responsible_unit"):
            score += 4
            reasons.append("same responsible_unit")

        shared_attendees = sorted(target_attendees & set(_normalized_people(candidate.get("attendees"))))
        if shared_attendees:
            score += min(len(shared_attendees) * 2, 6)
            reasons.append(f"shared attendees: {', '.join(shared_attendees[:3])}")

        candidate_owners = {item.get("owner") for item in candidate_items if _has_text(item.get("owner"))}
        shared_owners = sorted(target_owners & candidate_owners)
        if shared_owners:
            score += min(len(shared_owners) * 3, 6)
            reasons.append(f"shared owner: {shared_owners[0]}")

        candidate_keywords = _extract_keywords(candidate.get("meeting_name"))
        candidate_keywords.update(_extract_keywords(" ".join(item.get("content", "") for item in candidate_items)))
        shared_keywords = sorted((target_keywords & candidate_keywords), key=len, reverse=True)
        if shared_keywords:
            score += min(len(shared_keywords) * 2, 6)
            reasons.append(f"shared keyword: {shared_keywords[0]}")

        if score <= 0:
            continue

        related_results.append(
            {
                "meeting_id": candidate.get("meeting_id"),
                "meeting_name": candidate.get("meeting_name"),
                "meeting_date": candidate.get("meeting_date"),
                "reason": reasons,
                "score": float(score),
            }
        )

    related_results.sort(key=lambda item: (-item["score"], item.get("meeting_date") or "", item.get("meeting_id") or ""))
    return {
        "meeting_id": meeting_id,
        "related_meetings": related_results[:limit],
    }


def find_related_items(item_id: str, limit: int = 10) -> dict | None:
    items_collection = get_meeting_items_collection()
    minutes_collection = get_meeting_minutes_collection()

    target_item = items_collection.find_one({"item_id": item_id}, {"_id": 0})
    if not target_item:
        return None

    target_meeting = minutes_collection.find_one({"meeting_id": target_item.get("meeting_id")}, {"_id": 0}) or {}
    all_items = [doc for doc in items_collection.find({}, {"_id": 0}) if doc.get("item_id") != item_id]

    target_keywords = _extract_keywords(target_item.get("content"))
    target_owner = target_item.get("owner")
    target_tracking_blank = not _has_text(target_item.get("tracking_result"))
    target_planned_date = target_item.get("planned_date")
    target_meeting_keywords = _extract_keywords(target_meeting.get("meeting_name"))

    related_results = []
    for candidate in all_items:
        reasons = []
        score = 0.0
        candidate_meeting = minutes_collection.find_one({"meeting_id": candidate.get("meeting_id")}, {"_id": 0}) or {}

        shared_keywords = sorted((target_keywords & _extract_keywords(candidate.get("content"))), key=len, reverse=True)
        if shared_keywords:
            score += min(len(shared_keywords) * 3, 6)
            reasons.append(f"shared keyword: {shared_keywords[0]}")

        if _has_text(target_owner) and target_owner == candidate.get("owner"):
            score += 4
            reasons.append(f"same owner: {target_owner}")

        if _planned_dates_are_close(target_planned_date, candidate.get("planned_date")):
            score += 2
            reasons.append("planned_date is close")

        candidate_meeting_keywords = _extract_keywords(candidate_meeting.get("meeting_name"))
        shared_meeting_keywords = sorted((target_meeting_keywords & candidate_meeting_keywords), key=len, reverse=True)
        if shared_meeting_keywords:
            score += 2
            reasons.append(f"shared meeting keyword: {shared_meeting_keywords[0]}")

        candidate_tracking_blank = not _has_text(candidate.get("tracking_result"))
        if target_tracking_blank == candidate_tracking_blank:
            score += 1
            reasons.append("similar tracking status")

        if score <= 0:
            continue

        related_results.append(
            {
                "item_id": candidate.get("item_id"),
                "meeting_id": candidate.get("meeting_id"),
                "meeting_name": candidate_meeting.get("meeting_name"),
                "item_no": candidate.get("item_no"),
                "content": candidate.get("content"),
                "owner": candidate.get("owner"),
                "planned_date": candidate.get("planned_date"),
                "reason": reasons,
                "score": float(score),
            }
        )

    related_results.sort(key=lambda item: (-item["score"], item.get("planned_date") or "", item.get("item_id") or ""))
    return {
        "item_id": item_id,
        "related_items": [_serialize_mongo_document(item) for item in related_results[:limit]],
    }


def _extract_keywords(text) -> set[str]:
    if not text:
        return set()
    tokens = {token.lower() for token in TOKEN_PATTERN.findall(str(text))}
    return {token for token in tokens if token not in STOPWORDS and len(token) >= 2}


def _normalized_people(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        return [str(value).strip() for value in values if _has_text(value)]
    return [str(values).strip()] if _has_text(values) else []


def _planned_dates_are_close(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left[:7] == right[:7]


def _has_text(value) -> bool:
    return value is not None and str(value).strip() != ""
