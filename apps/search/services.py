from uuid import uuid4

from django.utils import timezone

from apps.meetings.services import _serialize_mongo_document

from .mongo import (
    ensure_indexes,
    get_meeting_items_collection,
    get_meeting_minutes_collection,
    get_search_click_logs_collection,
    get_search_logs_collection,
)
from .ranking import score_item, score_meeting


def search_meeting_minutes(
    q=None,
    date_from=None,
    date_to=None,
    responsible_unit=None,
    owner=None,
    chairperson=None,
    status=None,
    page=1,
    limit=10,
):
    ensure_indexes()
    meeting_query = {}
    if date_from or date_to:
        meeting_query["meeting_date"] = {}
        if date_from:
            meeting_query["meeting_date"]["$gte"] = date_from
        if date_to:
            meeting_query["meeting_date"]["$lte"] = date_to
    if responsible_unit:
        meeting_query["responsible_unit"] = responsible_unit
    if chairperson:
        meeting_query["chairperson"] = chairperson
    if status:
        meeting_query["status"] = status

    item_query = {}
    if owner:
        item_query["owner"] = {"$regex": owner, "$options": "i"}

    meetings_collection = get_meeting_minutes_collection()
    items_collection = get_meeting_items_collection()

    meetings = list(meetings_collection.find(meeting_query, {"_id": 0}))
    items = list(items_collection.find(item_query, {"_id": 0}))

    items_by_meeting_id = {}
    for item in items:
        items_by_meeting_id.setdefault(item["meeting_id"], []).append(item)

    results = []
    lowered_query = (q or "").strip()

    for meeting in meetings:
        candidate_items = items_by_meeting_id.get(meeting["meeting_id"], [])
        meeting_score, meeting_fields = score_meeting(meeting, lowered_query)

        matched_items = []
        item_score_total = 0
        matched_fields = list(meeting_fields)

        for item in candidate_items:
            item_score, item_fields = score_item(item, lowered_query)
            if lowered_query and item_score == 0:
                continue

            if owner and not item.get("owner"):
                continue

            matched_item = {
                "item_id": item["item_id"],
                "item_no": item.get("item_no"),
                "content": item.get("content"),
                "owner": item.get("owner"),
                "planned_date": item.get("planned_date"),
                "actual_completed_date": item.get("actual_completed_date"),
                "score": item_score,
            }
            matched_items.append(matched_item)
            item_score_total += item_score
            matched_fields.extend(item_fields)

        if owner and not matched_items:
            continue

        total_score = meeting_score + item_score_total
        if lowered_query and total_score == 0:
            continue

        if not lowered_query and not owner:
            matched_items = []

        results.append(
            {
                "meeting_id": meeting["meeting_id"],
                "document_id": meeting.get("document_id"),
                "meeting_name": meeting.get("meeting_name"),
                "meeting_date": meeting.get("meeting_date"),
                "responsible_unit": meeting.get("responsible_unit"),
                "score": total_score,
                "matched_fields": sorted(set(matched_fields)),
                "matched_items": matched_items,
            }
        )

    results.sort(key=lambda item: (-item["score"], item.get("meeting_date") or "", item.get("meeting_id") or ""))
    total = len(results)
    start = max(page - 1, 0) * limit
    paged_results = results[start:start + limit]

    search_log = _create_search_log(
        query=q or "",
        filters={
            "date_from": date_from,
            "date_to": date_to,
            "responsible_unit": responsible_unit,
            "owner": owner,
            "chairperson": chairperson,
            "status": status,
            "page": page,
            "limit": limit,
        },
        results=results,
    )

    return {
        "query": q or "",
        "search_id": search_log["search_id"],
        "total": total,
        "results": paged_results,
    }


def record_search_click(search_id, meeting_id, item_id=None, document_id=None):
    ensure_indexes()
    search_logs_collection = get_search_logs_collection()
    click_logs_collection = get_search_click_logs_collection()

    search_log = search_logs_collection.find_one({"search_id": search_id}, {"_id": 0})
    if not search_log:
        return None

    now = timezone.now()
    click_log = {
        "click_id": f"click_{uuid4().hex[:12]}",
        "search_id": search_id,
        "query": search_log.get("query", ""),
        "meeting_id": meeting_id,
        "item_id": item_id,
        "document_id": document_id,
        "created_at": now,
    }
    click_logs_collection.insert_one(click_log)
    return _serialize_mongo_document(click_log)


def _create_search_log(query, filters, results):
    search_logs_collection = get_search_logs_collection()
    now = timezone.now()
    search_log = {
        "search_id": f"search_{uuid4().hex[:12]}",
        "query": query,
        "filters": {key: value for key, value in filters.items() if value not in (None, "")},
        "result_count": len(results),
        "result_meeting_ids": [item["meeting_id"] for item in results],
        "created_at": now,
    }
    search_logs_collection.insert_one(search_log)
    return _serialize_mongo_document(search_log)
