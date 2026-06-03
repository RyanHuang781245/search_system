from __future__ import annotations

from collections import defaultdict

from . import cypher_queries as cq


def fetch_related_keywords(client, keyword: str, limit: int = 10) -> list[dict]:
    if not getattr(client, "available", False):
        return []
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return []
    return client.execute_read(_query_related_keywords, normalized_keyword, limit) or []


def search_graph(client, query: str, limit: int = 50) -> dict:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"query": "", "expanded_keywords": [], "results": []}
    if not getattr(client, "available", False):
        return {"query": normalized_query, "expanded_keywords": [], "results": []}

    related_keywords = fetch_related_keywords(client, normalized_query, limit=8)
    expanded_keywords = [normalized_query]
    expanded_keywords.extend(
        item["keyword"]
        for item in related_keywords
        if item.get("keyword") and item.get("keyword").upper() not in {value.upper() for value in expanded_keywords}
    )

    rows = client.execute_read(_query_graph_search, expanded_keywords) or []
    results = []
    for row in rows:
        matched_keyword = row.get("matched_keyword")
        match_type = "direct" if matched_keyword == normalized_query else "related"
        weight = 1.0 if match_type == "direct" else _find_related_weight(related_keywords, matched_keyword)
        graph_score = 3.0 if match_type == "direct" else round(max(weight * 2.5, 0.5), 2)
        results.append(
            {
                "meeting_id": row.get("meeting_id"),
                "meeting_name": row.get("meeting_name"),
                "meeting_date": row.get("meeting_date"),
                "item_id": row.get("item_id"),
                "item_no": row.get("item_no"),
                "content": row.get("content"),
                "matched_keyword": matched_keyword,
                "matched_field": row.get("matched_field"),
                "match_type": match_type,
                "graph_score": graph_score,
            }
        )

    results.sort(key=lambda item: (-item["graph_score"], item.get("meeting_date") or "", item.get("item_id") or ""))
    return {
        "query": normalized_query,
        "expanded_keywords": expanded_keywords[1:],
        "results": results[:limit],
    }


def build_graph_score_context(client, query: str) -> dict:
    payload = search_graph(client, query, limit=100)
    meeting_scores = defaultdict(float)
    item_scores = defaultdict(float)
    expanded_keywords = list(payload["expanded_keywords"])

    for row in payload["results"]:
        meeting_id = row.get("meeting_id")
        item_id = row.get("item_id")
        graph_score = float(row.get("graph_score") or 0)
        if meeting_id:
            meeting_scores[meeting_id] += graph_score
        if item_id:
            item_scores[item_id] += graph_score

    return {
        "expanded_keywords": expanded_keywords,
        "meeting_scores": dict(meeting_scores),
        "item_scores": dict(item_scores),
        "matches": payload["results"],
    }


def _query_related_keywords(tx, keyword: str, limit: int):
    records = tx.run(cq.QUERY_RELATED_KEYWORDS, keyword=keyword, limit=limit)
    return [
        {
            "keyword": record["keyword"],
            "type": record.get("type"),
            "weight": round(float(record.get("weight") or 0), 4),
            "count": int(record.get("count") or 0),
        }
        for record in records
    ]


def _query_graph_search(tx, keywords: list[str]):
    normalized_keywords = [str(keyword or "").strip().upper() for keyword in keywords if str(keyword or "").strip()]
    records = tx.run(cq.QUERY_GRAPH_SEARCH, keywords=normalized_keywords)
    return [dict(record) for record in records]


def _find_related_weight(related_keywords: list[dict], keyword: str) -> float:
    for item in related_keywords:
        if str(item.get("keyword") or "").upper() == str(keyword or "").upper():
            return float(item.get("weight") or 0)
    return 0.0
