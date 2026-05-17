from __future__ import annotations

from collections import Counter

from apps.meetings.services import _serialize_mongo_document

from .mongo import (
    get_meeting_items_collection,
    get_search_click_logs_collection,
    get_search_logs_collection,
)
from .ranking import has_owner_value


def get_search_stats(limit: int = 10) -> dict:
    search_logs = list(get_search_logs_collection().find({}, {"_id": 0}))
    click_logs = list(get_search_click_logs_collection().find({}, {"_id": 0}))
    meeting_items = list(get_meeting_items_collection().find({}, {"_id": 0}))

    query_counter = Counter(log.get("query", "") for log in search_logs if str(log.get("query", "")).strip())
    meeting_click_counter = Counter(log.get("meeting_id") for log in click_logs if log.get("meeting_id"))
    item_click_counter = Counter(log.get("item_id") for log in click_logs if log.get("item_id"))
    owner_counter = Counter(item.get("owner") for item in meeting_items if has_owner_value(item.get("owner")))

    recent_searches = sorted(search_logs, key=lambda item: item.get("created_at") or "", reverse=True)[:limit]

    return {
        "total_search_count": len(search_logs),
        "total_click_count": len(click_logs),
        "top_queries": [{"query": query, "count": count} for query, count in query_counter.most_common(limit)],
        "top_clicked_meetings": [
            {"meeting_id": meeting_id, "count": count}
            for meeting_id, count in meeting_click_counter.most_common(limit)
        ],
        "top_clicked_items": [
            {"item_id": item_id, "count": count}
            for item_id, count in item_click_counter.most_common(limit)
        ],
        "top_owners": [{"owner": owner, "count": count} for owner, count in owner_counter.most_common(limit)],
        "recent_searches": [_serialize_mongo_document(item) for item in recent_searches],
    }
