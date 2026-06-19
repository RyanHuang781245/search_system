from __future__ import annotations

from uuid import uuid4

from django.utils import timezone

from apps.meetings.services import _serialize_mongo_document
from apps.graph.services import get_graph_score_context
from apps.item_status import item_status_payload

from .feedback import build_feedback_context, score_item_feedback, score_meeting_feedback
from .highlighter import collect_matched_snippets
from .mongo import (
    ensure_indexes,
    get_meeting_items_collection,
    get_meeting_minutes_collection,
    get_search_click_logs_collection,
    get_search_logs_collection,
)
from .ranking import (
    finalize_item_score,
    finalize_meeting_score,
    has_owner_value,
    has_value,
    score_item,
    score_meeting_metadata,
    score_recency,
)
from .recommender import find_related_items, find_related_meetings
from .stats import get_search_stats


def search_meeting_minutes(
    q=None,
    date_from=None,
    date_to=None,
    responsible_unit=None,
    owner=None,
    chairperson=None,
    has_owner=None,
    has_planned_date=None,
    is_completed=None,
    has_tracking_result=None,
    status=None,
    sort_by=None,
    page=1,
    limit=10,
):
    ensure_indexes()

    query = (q or "").strip()
    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    feedback_context = build_feedback_context(query)
    graph_context = _get_safe_graph_context(query)

    meetings = [meeting for meeting in meetings if _meeting_matches_filters(meeting, date_from, date_to, responsible_unit, chairperson, status)]

    items_by_meeting_id = {}
    for item in items:
        items_by_meeting_id.setdefault(item.get("meeting_id"), []).append(item)

    item_filters_active = any(value is not None for value in (owner, has_owner, has_planned_date, is_completed, has_tracking_result))

    results = []
    for meeting in meetings:
        meeting_id = meeting.get("meeting_id")
        meeting_items = items_by_meeting_id.get(meeting_id, [])
        filtered_items = [
            item
            for item in meeting_items
            if _item_matches_filters(
                item,
                owner=owner,
                has_owner=has_owner,
                has_planned_date=has_planned_date,
                is_completed=is_completed,
                has_tracking_result=has_tracking_result,
            )
        ]

        if item_filters_active and not filtered_items:
            continue

        meeting_score_detail = score_meeting_metadata(meeting, query)
        recency_score = score_recency(meeting.get("meeting_date"))
        meeting_feedback_score = score_meeting_feedback(meeting_id, feedback_context)
        meeting_graph_score = float(graph_context["meeting_scores"].get(meeting_id, 0))

        matched_items = []
        aggregate_keyword = meeting_score_detail["keyword_score"]
        aggregate_structure = meeting_score_detail["structure_score"]
        aggregate_task = 0.0
        aggregate_feedback = meeting_feedback_score
        aggregate_graph = meeting_graph_score
        matched_fields = list(meeting_score_detail["matched_fields"])

        for item in filtered_items:
            item_score_detail = score_item(item, query)
            item_feedback_score = score_item_feedback(item.get("item_id"), feedback_context)
            item_graph_score = float(graph_context["item_scores"].get(item.get("item_id"), 0))
            item_score_detail["feedback_score"] = float(item_feedback_score)
            item_score_detail["graph_score"] = item_graph_score
            item_final_score = finalize_item_score(item_score_detail)

            include_item = True
            if query and item_score_detail["keyword_score"] == 0 and item_graph_score == 0 and not owner and not item_filters_active:
                include_item = False

            if include_item:
                matched_item = {
                    "item_id": item.get("item_id"),
                    "item_no": item.get("item_no"),
                    "content": item.get("content"),
                    "owner": item.get("owner"),
                    "planned_date": item.get("planned_date"),
                    "actual_completed_date": item.get("actual_completed_date"),
                    "tracking_result": item.get("tracking_result"),
                    "status": item_status_payload(item)["status"],
                    "status_source": item_status_payload(item)["source"],
                    "status_confidence": item_status_payload(item)["confidence"],
                    "final_score": item_final_score,
                    "score_detail": _round_score_detail(item_score_detail),
                }
                matched_items.append(matched_item)
                aggregate_keyword += item_score_detail["keyword_score"]
                aggregate_structure += item_score_detail["structure_score"]
                aggregate_task += item_score_detail["task_score"]
                aggregate_feedback += item_feedback_score
                matched_fields.extend(item_score_detail["matched_fields"])

        meeting_total_score_detail = {
            "keyword_score": float(aggregate_keyword),
            "structure_score": float(aggregate_structure),
            "task_score": float(aggregate_task),
            "recency_score": float(recency_score),
            "feedback_score": float(aggregate_feedback),
            "graph_score": float(aggregate_graph),
        }
        final_score = finalize_meeting_score(meeting_total_score_detail)

        if query and final_score <= 0:
            continue

        if not query and not item_filters_active and not owner:
            matched_items = []

        matched_items.sort(key=lambda item: (-item["final_score"], item.get("item_no") or "", item.get("item_id") or ""))

        result = {
            "meeting_id": meeting_id,
            "document_id": meeting.get("document_id"),
            "meeting_name": meeting.get("meeting_name"),
            "meeting_date": meeting.get("meeting_date"),
            "responsible_unit": meeting.get("responsible_unit"),
            "final_score": final_score,
            "score_detail": _round_score_detail(meeting_total_score_detail),
            "matched_fields": sorted(set(matched_fields)),
            "matched_snippets": collect_matched_snippets(
                query,
                meeting,
                filtered_items if matched_items else [],
                extra_terms=graph_context["expanded_keywords"],
            ),
            "matched_items": matched_items,
        }
        results.append(result)

    _sort_search_results(results, sort_by)

    total = len(results)
    start = max(page - 1, 0) * limit
    paged_results = results[start:start + limit]

    search_log = _create_search_log(
        query=query,
        filters={
            "date_from": date_from,
            "date_to": date_to,
            "responsible_unit": responsible_unit,
            "owner": owner,
            "chairperson": chairperson,
            "has_owner": has_owner,
            "has_planned_date": has_planned_date,
            "is_completed": is_completed,
            "has_tracking_result": has_tracking_result,
            "status": status,
            "sort_by": sort_by,
            "page": page,
            "limit": limit,
        },
        results=results,
    )

    return {
        "query": query,
        "search_id": search_log["search_id"],
        "total": total,
        "expanded_keywords_from_graph": graph_context["expanded_keywords"],
        "results": paged_results,
    }


def record_search_click(search_id, meeting_id, item_id=None, document_id=None):
    ensure_indexes()
    search_log = get_search_logs_collection().find_one({"search_id": search_id}, {"_id": 0})
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
    get_search_click_logs_collection().insert_one(click_log)
    return _serialize_mongo_document(click_log)


def get_related_meetings(meeting_id, limit=10):
    ensure_indexes()
    return find_related_meetings(meeting_id, limit=limit)


def get_related_items(item_id, limit=10):
    ensure_indexes()
    return find_related_items(item_id, limit=limit)


def get_stats(limit=10):
    ensure_indexes()
    return get_search_stats(limit=limit)


def _create_search_log(query, filters, results):
    now = timezone.now()
    search_log = {
        "search_id": f"search_{uuid4().hex[:12]}",
        "query": query,
        "filters": {key: value for key, value in filters.items() if value not in (None, "")},
        "result_count": len(results),
        "result_meeting_ids": [item["meeting_id"] for item in results],
        "created_at": now,
    }
    get_search_logs_collection().insert_one(search_log)
    return _serialize_mongo_document(search_log)


def _meeting_matches_filters(meeting, date_from, date_to, responsible_unit, chairperson, status):
    meeting_date = meeting.get("meeting_date") or ""
    if date_from and meeting_date and meeting_date < date_from:
        return False
    if date_to and meeting_date and meeting_date > date_to:
        return False
    if responsible_unit and meeting.get("responsible_unit") != responsible_unit:
        return False
    if chairperson and chairperson.lower() not in str(meeting.get("chairperson") or "").lower():
        return False
    if status and meeting.get("status") != status:
        return False
    return True


def _item_matches_filters(item, owner, has_owner, has_planned_date, is_completed, has_tracking_result):
    if owner and owner.lower() not in str(item.get("owner") or "").lower():
        return False

    owner_present = has_owner_value(item.get("owner"))
    planned_date_present = has_value(item.get("planned_date"))
    status_payload = item_status_payload(item)
    completed = status_payload["status"] == "completed"
    tracking_result_present = has_value(item.get("tracking_result"))

    if has_owner is True and not owner_present:
        return False
    if has_owner is False and owner_present:
        return False
    if has_planned_date is True and not planned_date_present:
        return False
    if has_planned_date is False and planned_date_present:
        return False
    if is_completed is True and not completed:
        return False
    if is_completed is False and completed:
        return False
    if has_tracking_result is True and not tracking_result_present:
        return False
    if has_tracking_result is False and tracking_result_present:
        return False

    return True


def _sort_search_results(results, sort_by):
    sort_key = (sort_by or "final_score").strip().lower()

    if sort_key in {"meeting_date_asc", "date_asc", "oldest"}:
        results.sort(key=lambda item: (item.get("meeting_date") or "9999-12-31", -item.get("final_score", 0), item.get("meeting_id") or ""))
        return
    if sort_key in {"meeting_date_desc", "date_desc", "recent", "latest"}:
        results.sort(key=lambda item: (item.get("meeting_date") or "", item.get("final_score", 0), item.get("meeting_id") or ""), reverse=True)
        return
    if sort_key in {"feedback", "feedback_score"}:
        results.sort(
            key=lambda item: (
                -item.get("score_detail", {}).get("feedback_score", 0),
                -(item.get("final_score") or 0),
                item.get("meeting_date") or "",
                item.get("meeting_id") or "",
            )
        )
        return
    if sort_key in {"keyword", "keyword_score"}:
        results.sort(
            key=lambda item: (
                -item.get("score_detail", {}).get("keyword_score", 0),
                -(item.get("final_score") or 0),
                item.get("meeting_date") or "",
                item.get("meeting_id") or "",
            )
        )
        return
    if sort_key in {"graph", "graph_score"}:
        results.sort(
            key=lambda item: (
                -item.get("score_detail", {}).get("graph_score", 0),
                -(item.get("final_score") or 0),
                item.get("meeting_date") or "",
                item.get("meeting_id") or "",
            )
        )
        return

    results.sort(key=lambda item: (-(item.get("final_score") or 0), item.get("meeting_date") or "", item.get("meeting_id") or ""))


def _round_score_detail(score_detail):
    return {
        key: round(float(value), 2)
        for key, value in score_detail.items()
        if isinstance(value, (int, float))
    }


def _get_safe_graph_context(query: str) -> dict:
    if not query:
        return {"expanded_keywords": [], "meeting_scores": {}, "item_scores": {}, "matches": []}
    try:
        return get_graph_score_context(query)
    except Exception:
        return {"expanded_keywords": [], "meeting_scores": {}, "item_scores": {}, "matches": []}
