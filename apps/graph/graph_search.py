from __future__ import annotations

from collections import defaultdict

from . import cypher_queries as cq
from .intent import analyze_graph_intent


def fetch_related_keywords(client, keyword: str, limit: int = 10) -> list[dict]:
    if not getattr(client, "available", False):
        return []
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return []
    return client.execute_read(_query_related_keywords, normalized_keyword, limit) or []


def search_graph(client, query: str, limit: int = 50, intent_analyzer=None) -> dict:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"query": "", "expanded_keywords": [], "results": [], "warnings": []}
    if not getattr(client, "available", False):
        return {
            "query": normalized_query,
            "expanded_keywords": [],
            "results": [],
            "warnings": ["Neo4j graph search unavailable."],
        }

    intent_payload = run_intent_analysis(normalized_query, intent_analyzer)
    intent_results = search_intent_graph(client, intent_payload, limit=limit)
    related_keywords = fetch_related_keywords(client, normalized_query, limit=8)
    expanded_keywords = [normalized_query]
    expanded_keywords.extend(
        item["keyword"]
        for item in related_keywords
        if item.get("keyword") and item.get("keyword").upper() not in {value.upper() for value in expanded_keywords}
    )

    rows = client.execute_read(_query_graph_search, expanded_keywords) or []
    keyword_results = []
    for row in rows:
        matched_keyword = row.get("matched_keyword")
        match_type = "direct" if matched_keyword == normalized_query else "related"
        weight = 1.0 if match_type == "direct" else _find_related_weight(related_keywords, matched_keyword)
        graph_score = 3.0 if match_type == "direct" else round(max(weight * 2.5, 0.5), 2)
        keyword_results.append(
            {
                "meeting_id": row.get("meeting_id"),
                "meeting_name": row.get("meeting_name"),
                "meeting_date": row.get("meeting_date"),
                "item_id": row.get("item_id"),
                "item_no": row.get("item_no"),
                "content": row.get("content"),
                "matched_keyword": matched_keyword,
                "matched_field": row.get("matched_field"),
                "matched_relation": "MENTIONS",
                "matched_entity": matched_keyword,
                "keyword_score": row.get("keyword_score"),
                "keyword_method": row.get("keyword_method"),
                "match_type": match_type,
                "intent": "keyword_related",
                "graph_score": graph_score,
            }
        )

    results = dedupe_graph_results([*intent_results, *keyword_results])
    results.sort(key=lambda item: (-item["graph_score"], item.get("meeting_date") or "", item.get("item_id") or ""))
    return {
        "query": normalized_query,
        "intent": intent_payload["intent"],
        "intent_entities": intent_payload["entities"],
        "expanded_keywords": expanded_keywords[1:],
        "results": results[:limit],
        "warnings": intent_payload.get("warnings", []),
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


def run_intent_analysis(query: str, intent_analyzer) -> dict:
    if intent_analyzer is None:
        return {"intent": "keyword_related", "entities": {}, "warnings": []}
    try:
        payload = intent_analyzer(query)
    except Exception as exc:
        return {
            "intent": "keyword_related",
            "entities": {},
            "warnings": [f"Graph intent analysis unavailable: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "intent": "keyword_related",
            "entities": {},
            "warnings": ["Graph intent analysis returned an invalid payload."],
        }
    return {
        "intent": payload.get("intent") or "keyword_related",
        "entities": payload.get("entities") or {},
        "warnings": payload.get("warnings") or [],
    }


def search_intent_graph(client, intent_payload: dict, limit: int) -> list[dict]:
    intent = intent_payload.get("intent")
    spec = get_intent_query_spec(intent)
    if spec is None:
        return []

    entity = extract_entity(intent, intent_payload.get("entities") or {})
    rows = client.execute_read(_query_intent_graph_search, spec, entity, limit) or []
    return [format_intent_result(row, intent, entity) for row in rows]


def get_intent_query_spec(intent: str) -> dict | None:
    return {
        "person_responsibility": {"query": cq.QUERY_RESPONSIBLE_ITEMS},
        "person_attendance": {"query": cq.QUERY_MEETING_PERSON_RELATION, "relation": "ATTENDED_BY"},
        "meeting_chair": {"query": cq.QUERY_MEETING_PERSON_RELATION, "relation": "CHAIRED_BY"},
        "meeting_recorder": {"query": cq.QUERY_MEETING_PERSON_RELATION, "relation": "RECORDED_BY"},
        "unit_meetings": {"query": cq.QUERY_UNIT_MEETINGS},
        "planned_date": {"query": cq.QUERY_ITEM_DATE_RELATION, "relation": "HAS_PLANNED_DATE"},
        "completed_date": {"query": cq.QUERY_ITEM_DATE_RELATION, "relation": "HAS_COMPLETED_DATE"},
        "product_related": {"query": cq.QUERY_ITEM_PRODUCT_RELATION},
        "regulation_related": {"query": cq.QUERY_ITEM_REGULATION_RELATION},
    }.get(intent)


def extract_entity(intent: str, entities: dict) -> str:
    entity_key_by_intent = {
        "person_responsibility": "person_name",
        "person_attendance": "person_name",
        "meeting_chair": "person_name",
        "meeting_recorder": "person_name",
        "unit_meetings": "unit_name",
        "planned_date": "date_value",
        "completed_date": "date_value",
        "product_related": "product_name",
        "regulation_related": "regulation_name",
    }
    return str(entities.get(entity_key_by_intent.get(intent, "keyword")) or "").strip()


def _query_intent_graph_search(tx, spec: dict, entity: str, limit: int):
    records = tx.run(
        spec["query"],
        entity=str(entity or "").strip().upper(),
        relation=spec.get("relation", ""),
        limit=limit,
    )
    return [dict(record) for record in records][:limit]


def format_intent_result(row: dict, intent: str, query_entity: str) -> dict:
    matched_relation = row.get("matched_relation")
    matched_entity = row.get("matched_entity") or query_entity
    return {
        "meeting_id": row.get("meeting_id"),
        "meeting_name": row.get("meeting_name"),
        "meeting_date": row.get("meeting_date"),
        "item_id": row.get("item_id"),
        "item_no": row.get("item_no"),
        "content": row.get("content"),
        "matched_keyword": None,
        "matched_field": row.get("matched_field"),
        "matched_relation": matched_relation,
        "matched_entity": matched_entity,
        "match_type": "intent",
        "intent": intent,
        "graph_score": 4.0,
    }


def dedupe_graph_results(results: list[dict]) -> list[dict]:
    by_key = {}
    for result in results:
        key = (
            result.get("meeting_id"),
            result.get("item_id"),
            result.get("matched_relation"),
            result.get("matched_entity"),
            result.get("matched_keyword"),
        )
        existing = by_key.get(key)
        if existing is None or float(result.get("graph_score") or 0) > float(existing.get("graph_score") or 0):
            by_key[key] = result
    return list(by_key.values())


def _find_related_weight(related_keywords: list[dict], keyword: str) -> float:
    for item in related_keywords:
        if str(item.get("keyword") or "").upper() == str(keyword or "").upper():
            return float(item.get("weight") or 0)
    return 0.0
