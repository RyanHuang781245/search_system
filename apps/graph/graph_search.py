from __future__ import annotations

from collections import defaultdict
import re

from . import cypher_queries as cq
from .intent import analyze_graph_intent
from .query_planner import default_plan


def fetch_related_keywords(client, keyword: str, limit: int = 10) -> list[dict]:
    if not getattr(client, "available", False):
        return []
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return []
    return client.execute_read(_query_related_keywords, normalized_keyword, limit) or []


def search_graph(
    client,
    query: str,
    limit: int = 50,
    intent_analyzer=None,
    query_planner=None,
    retrieval_modes=None,
) -> dict:
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

    modes = normalize_retrieval_modes(retrieval_modes)
    meeting_item_results = search_meeting_items_by_query(client, normalized_query, limit=limit) if "structural" in modes else []
    if meeting_item_results:
        return {
            "query": normalized_query,
            "query_plan": {
                "target": "meeting_items",
                "constraints": {},
                "include_followups": False,
            },
            "intent": "meeting_items",
            "intent_entities": {},
            "expanded_keywords": [],
            "retrieval_modes": list(modes),
            "results": meeting_item_results[:limit],
            "warnings": [],
        }
    follow_up_results = search_issue_timeline_graph(client, normalized_query, limit=limit) if "follow_up" in modes else []
    intent_payload = run_intent_analysis(normalized_query, intent_analyzer) if "relation" in modes else {
        "intent": "keyword_related",
        "entities": {},
        "warnings": [],
    }
    if intent_payload.get("intent") in {"planned_date", "completed_date"}:
        intent_results = search_intent_graph(client, intent_payload, limit=limit)
        if intent_results:
            return {
                "query": normalized_query,
                "query_plan": {
                    "target": "meeting_items",
                    "constraints": {},
                    "include_followups": False,
                },
                "intent": intent_payload["intent"],
                "intent_entities": intent_payload["entities"],
                "expanded_keywords": [],
                "retrieval_modes": list(modes),
                "results": intent_results[:limit],
                "warnings": intent_payload.get("warnings", []),
            }
    planner_payload = run_query_planning(normalized_query, query_planner) if "composite" in modes else default_plan()
    composite_results = search_composite_graph(client, planner_payload, limit=limit) if "composite" in modes else []
    intent_results = search_intent_graph(client, intent_payload, limit=limit) if "relation" in modes else []
    related_keywords = fetch_related_keywords(client, normalized_query, limit=8) if "keyword" in modes else []
    expanded_keywords = [normalized_query]
    expanded_keywords.extend(
        item["keyword"]
        for item in related_keywords
        if item.get("keyword") and item.get("keyword").upper() not in {value.upper() for value in expanded_keywords}
    )

    rows = client.execute_read(_query_graph_search, expanded_keywords) if "keyword" in modes else []
    rows = rows or []
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
                "retrieval_mode": "keyword",
                "graph_score": graph_score,
            }
        )

    if meeting_item_results or follow_up_results or composite_results or intent_results:
        keyword_results = [result for result in keyword_results if result.get("match_type") == "direct"]

    results = dedupe_graph_results([*meeting_item_results, *follow_up_results, *composite_results, *intent_results, *keyword_results])
    results.sort(key=lambda item: (-item["graph_score"], item.get("meeting_date") or "", item.get("item_id") or ""))
    return {
        "query": normalized_query,
        "query_plan": {
            "target": "issues" if "follow_up" in modes else planner_payload.get("target"),
            "constraints": planner_payload.get("constraints", {}),
            "include_followups": True if "follow_up" in modes else planner_payload.get("include_followups", False),
        },
        "intent": "follow_up_tracking" if "follow_up" in modes else intent_payload["intent"],
        "intent_entities": intent_payload["entities"],
        "expanded_keywords": expanded_keywords[1:],
        "retrieval_modes": list(modes),
        "results": results[:limit],
        "warnings": planner_payload.get("warnings", []) + intent_payload.get("warnings", []),
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


def normalize_retrieval_modes(retrieval_modes) -> tuple[str, ...]:
    default_modes = ("structural", "composite", "relation", "keyword")
    supported = ("structural", "composite", "relation", "keyword", "follow_up")
    if retrieval_modes is None:
        return default_modes
    if isinstance(retrieval_modes, str):
        raw_modes = [retrieval_modes]
    else:
        raw_modes = list(retrieval_modes or [])
    modes = []
    for mode in raw_modes:
        normalized = str(mode or "").strip().lower()
        if normalized in supported and normalized not in modes:
            modes.append(normalized)
    return tuple(modes or default_modes)


def search_meeting_items_by_query(client, query: str, limit: int) -> list[dict]:
    if not looks_like_meeting_item_list_query(query):
        return []
    rows = client.execute_read(_query_meeting_items_by_query, query, limit) or []
    return [format_meeting_item_result(row) for row in rows]


def looks_like_meeting_item_list_query(query: str) -> bool:
    text = str(query or "").lower()
    has_meeting_cue = any(term in text for term in ("會議", "meeting"))
    has_item_cue = any(
        term in text
        for term in ("項目", "事項", "討論事項", "議題", "item", "agenda", "topic", "內容", "包含", "有哪些", "哪些")
    )
    return has_meeting_cue and has_item_cue


def _query_meeting_items_by_query(tx, query: str, limit: int):
    records = tx.run(cq.QUERY_MEETING_ITEMS_BY_QUERY, question=query, terms=meeting_query_terms(query), limit=limit)
    return [dict(record) for record in records][:limit]


def format_meeting_item_result(row: dict) -> dict:
    return {
        "meeting_id": row.get("meeting_id"),
        "meeting_name": row.get("meeting_name"),
        "meeting_date": row.get("meeting_date"),
        "item_id": row.get("item_id"),
        "item_no": row.get("item_no"),
        "content": row.get("content"),
        "matched_keyword": None,
        "matched_field": row.get("matched_field"),
        "matched_relation": "HAS_ITEM",
        "matched_entity": row.get("matched_entity"),
        "match_type": "meeting_items",
        "intent": "meeting_items",
        "retrieval_mode": "structural",
        "graph_score": 5.2,
    }


def meeting_query_terms(query: str) -> list[str]:
    text = str(query or "")
    for cue in (
        "會議",
        "項目",
        "討論事項",
        "事項",
        "議題",
        "內容",
        "包含",
        "有哪些",
        "哪些",
        "列出",
        "請問",
        "的",
        "which",
        "items",
        "agenda",
        "topics",
        "topic",
        "included",
        "include",
        "meeting",
        "content",
    ):
        text = re.sub(re.escape(cue), " ", text, flags=re.I)
    terms = []
    for token in re.split(r"[\s,，。；;:：?？()（）\[\]【】]+", text):
        cleaned = token.strip()
        if len(cleaned) >= 2:
            terms.append(cleaned.upper())
    return terms[:8]

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


def run_query_planning(query: str, query_planner) -> dict:
    if query_planner is None:
        return default_plan()
    planner = query_planner
    try:
        payload = planner(query)
    except Exception as exc:
        return {
            "target": "meeting_items",
            "constraints": {},
            "include_followups": False,
            "warnings": [f"Graph query planning unavailable: {exc}"],
        }
    if not isinstance(payload, dict):
        return {
            "target": "meeting_items",
            "constraints": {},
            "include_followups": False,
            "warnings": ["Graph query planning returned an invalid payload."],
        }
    return {
        "target": payload.get("target") or "meeting_items",
        "constraints": payload.get("constraints") or {},
        "include_followups": bool(payload.get("include_followups")),
        "warnings": payload.get("warnings") or [],
    }


def search_composite_graph(client, planner_payload: dict, limit: int) -> list[dict]:
    target = planner_payload.get("target") or "meeting_items"
    constraints = planner_payload.get("constraints") or {}
    if target == "meeting_items":
        return []
    if target == "action_items" and not has_composite_constraints(constraints):
        return []

    rows = client.execute_read(_query_composite_graph_search, target, constraints, limit) or []
    results = [format_composite_result(row, planner_payload) for row in rows]
    if planner_payload.get("include_followups"):
        follow_up_rows = client.execute_read(_query_follow_up_graph_search, constraints, limit) or []
        results.extend(format_follow_up_result(row, planner_payload) for row in follow_up_rows)
    return results


def _query_composite_graph_search(tx, target: str, constraints: dict, limit: int):
    params = normalize_composite_params(target, constraints, limit)
    records = tx.run(cq.QUERY_COMPOSITE_GRAPH_SEARCH, **params)
    return [dict(record) for record in records][:limit]


def _query_follow_up_graph_search(tx, constraints: dict, limit: int):
    params = {
        "keyword": str(constraints.get("keyword") or constraints.get("product_name") or constraints.get("regulation_name") or "")
        .strip()
        .upper(),
        "limit": limit,
    }
    records = tx.run(cq.QUERY_FOLLOW_UP_ITEMS, **params)
    return [dict(record) for record in records][:limit]


def normalize_composite_params(target: str, constraints: dict, limit: int) -> dict:
    return {
        "target": target if target in {"action_items", "decisions", "risks", "issues"} else "action_items",
        "person": str(constraints.get("person_name") or "").strip().upper(),
        "unit": str(constraints.get("unit_name") or "").strip().upper(),
        "product": str(constraints.get("product_name") or "").strip().upper(),
        "regulation": str(constraints.get("regulation_name") or "").strip().upper(),
        "status": str(constraints.get("status") or "").strip(),
        "keyword": str(constraints.get("keyword") or "").strip().upper(),
        "limit": limit,
    }


def has_composite_constraints(constraints: dict) -> bool:
    return any(str(constraints.get(key) or "").strip() for key in (
        "person_name",
        "unit_name",
        "product_name",
        "regulation_name",
        "status",
        "keyword",
    ))


def format_composite_result(row: dict, planner_payload: dict) -> dict:
    relation = row.get("matched_relation") or "HAS_ACTION"
    return {
        "meeting_id": row.get("meeting_id"),
        "meeting_name": row.get("meeting_name"),
        "meeting_date": row.get("meeting_date"),
        "item_id": row.get("item_id"),
        "item_no": row.get("item_no"),
        "content": row.get("content"),
        "matched_keyword": None,
        "matched_field": row.get("matched_field"),
        "matched_relation": relation,
        "matched_entity": row.get("matched_entity") or row.get("matched_node_id"),
        "matched_node_id": row.get("matched_node_id"),
        "semantic_status": row.get("semantic_status"),
        "semantic_status_source": row.get("semantic_status_source"),
        "semantic_status_confidence": row.get("semantic_status_confidence"),
        "evidence_relations": build_composite_evidence_relations(row, planner_payload),
        "match_type": "query_plan",
        "intent": planner_payload.get("target"),
        "query_plan": planner_payload,
        "retrieval_mode": "composite",
        "graph_score": graph_score_for_semantic_relation(relation),
    }


def format_follow_up_result(row: dict, planner_payload: dict) -> dict:
    return {
        "meeting_id": row.get("meeting_id"),
        "meeting_name": row.get("meeting_name"),
        "meeting_date": row.get("meeting_date"),
        "item_id": row.get("item_id"),
        "item_no": row.get("item_no"),
        "content": row.get("content"),
        "matched_keyword": None,
        "matched_field": "follow_up",
        "matched_relation": "FOLLOW_UP_OF",
        "matched_entity": row.get("matched_entity"),
        "matched_node_id": row.get("matched_node_id"),
        "match_type": "query_plan",
        "intent": "follow_up",
        "query_plan": planner_payload,
        "retrieval_mode": "composite",
        "graph_score": 4.4,
    }


def search_issue_timeline_graph(client, query: str, limit: int) -> list[dict]:
    keyword = follow_up_query_keyword(query)
    rows = client.execute_read(_query_issue_timeline_graph_search, keyword, limit) or []
    results = [format_issue_timeline_result(row) for row in rows]
    sequence_by_group = defaultdict(int)
    for result in results:
        group = result.get("timeline_group") or result.get("issue_id") or "unknown_issue"
        sequence_by_group[group] += 1
        result["sequence_no"] = sequence_by_group[group]
    return results


def _query_issue_timeline_graph_search(tx, keyword: str, limit: int):
    records = tx.run(cq.QUERY_ISSUE_TIMELINE, keyword=str(keyword or "").strip().upper(), limit=limit)
    return [dict(record) for record in records][:limit]


def format_issue_timeline_result(row: dict) -> dict:
    issue_id = row.get("issue_id") or row.get("matched_node_id") or row.get("issue_title")
    issue_title = row.get("issue_title") or row.get("matched_entity") or issue_id
    item_id = row.get("item_id")
    previous_item_id = row.get("previous_item_id")
    next_item_id = row.get("next_item_id")
    result = {
        "meeting_id": row.get("meeting_id"),
        "meeting_name": row.get("meeting_name"),
        "meeting_date": row.get("meeting_date"),
        "item_id": item_id,
        "item_no": row.get("item_no"),
        "content": row.get("content"),
        "matched_keyword": None,
        "matched_field": "issue_timeline",
        "matched_relation": "TRACKS_ISSUE",
        "matched_entity": issue_title,
        "matched_node_id": issue_id,
        "issue_id": issue_id,
        "issue_title": issue_title,
        "issue_signature": row.get("issue_signature"),
        "timeline_group": issue_id,
        "previous_item_id": previous_item_id,
        "previous_meeting_id": row.get("previous_meeting_id"),
        "next_item_id": next_item_id,
        "next_meeting_id": row.get("next_meeting_id"),
        "evidence_relations": build_issue_timeline_evidence_relations(
            item_id=item_id,
            issue_id=issue_id,
            issue_title=issue_title,
            previous_item_id=previous_item_id,
            next_item_id=next_item_id,
        ),
        "match_type": "issue_timeline",
        "intent": "follow_up_tracking",
        "retrieval_mode": "follow_up",
        "graph_score": 4.7,
    }
    return result


def build_issue_timeline_evidence_relations(
    *,
    item_id: str | None,
    issue_id: str | None,
    issue_title: str | None,
    previous_item_id: str | None,
    next_item_id: str | None,
) -> list[dict]:
    evidence = []
    if item_id and issue_id:
        evidence.append(
            make_evidence_relation("MeetingItem", item_id, "Issue", issue_id, "TRACKS_ISSUE", issue_title)
        )
    if item_id and previous_item_id:
        evidence.append(
            make_evidence_relation("MeetingItem", item_id, "MeetingItem", previous_item_id, "FOLLOW_UP_OF")
        )
    if item_id and next_item_id:
        evidence.append(
            make_evidence_relation("MeetingItem", next_item_id, "MeetingItem", item_id, "FOLLOW_UP_OF")
        )
    return evidence


def follow_up_query_keyword(query: str) -> str:
    text = str(query or "").strip()
    regulation = re.search(r"\b(FDA|TFDA|CFDA|PMDA|CE|ISO\s*\d*)\b", text, flags=re.I)
    if regulation:
        return regulation.group(1)
    english_phrases = re.findall(r"[A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,3}", text)
    cleaned_phrases = [
        phrase.strip()
        for phrase in english_phrases
        if phrase.strip().lower() not in {"follow up", "issue tracking"}
    ]
    if cleaned_phrases:
        return max(cleaned_phrases, key=len)
    cleaned = text
    for cue in (
        "跨會議追蹤",
        "追蹤事項",
        "後續追蹤",
        "後續狀況",
        "後來怎麼處理",
        "後來如何處理",
        "相關",
        "整理",
        "有哪些",
        "哪些",
        "會議",
        "事項",
        "狀況",
    ):
        cleaned = cleaned.replace(cue, " ")
    tokens = [token.strip() for token in re.split(r"[\s,，。；;:：?？()（）\[\]【】]+", cleaned) if len(token.strip()) >= 2]
    return tokens[0] if tokens else ""


def graph_score_for_semantic_relation(relation: str) -> float:
    return {
        "HAS_ACTION": 3.8,
        "HAS_DECISION": 4.8,
        "HAS_RISK": 4.9,
        "TRACKS_ISSUE": 4.5,
        "FOLLOW_UP_OF": 4.4,
    }.get(relation, 4.2)


def build_composite_evidence_relations(row: dict, planner_payload: dict) -> list[dict]:
    item_id = row.get("item_id")
    meeting_id = row.get("meeting_id")
    matched_node_id = row.get("matched_node_id")
    matched_entity = row.get("matched_entity")
    relation = row.get("matched_relation") or "HAS_ACTION"
    constraints = planner_payload.get("constraints") or {}
    evidence = []

    if item_id and matched_node_id and relation in {"HAS_ACTION", "HAS_DECISION", "HAS_RISK", "TRACKS_ISSUE"}:
        evidence.append(
            {
                "source_type": "MeetingItem",
                "source_value": item_id,
                "target_type": semantic_target_type_for_relation(relation),
                "target_value": matched_node_id,
                "target_label": matched_entity,
                "relation": relation,
            }
        )

    person = constraints.get("person_name")
    for owner in filter_matching_values(row.get("owner_names"), person):
        evidence.append(make_evidence_relation("MeetingItem", item_id, "Person", owner, "RESPONSIBLE_BY"))
    for assignee in filter_matching_values(row.get("assignee_names"), person):
        evidence.append(make_evidence_relation("ActionItem", matched_node_id, "Person", assignee, "ASSIGNED_TO"))

    unit = constraints.get("unit_name")
    for unit_name in filter_matching_values(row.get("unit_names"), unit):
        evidence.append(make_evidence_relation("Meeting", meeting_id, "Unit", unit_name, "BELONGS_TO_UNIT"))

    product = constraints.get("product_name")
    for product_name in filter_matching_values(row.get("product_names"), product):
        evidence.append(make_evidence_relation("MeetingItem", item_id, "Product", product_name, "MENTIONS_PRODUCT"))
    for product_name in filter_matching_values(row.get("action_product_names"), product):
        evidence.append(make_evidence_relation("ActionItem", matched_node_id, "Product", product_name, "TARGETS_PRODUCT"))

    regulation = constraints.get("regulation_name")
    for regulation_name in filter_matching_values(row.get("regulation_names"), regulation):
        evidence.append(
            make_evidence_relation("MeetingItem", item_id, "Regulation", regulation_name, "MENTIONS_REGULATION")
        )
    for regulation_name in filter_matching_values(row.get("action_regulation_names"), regulation):
        evidence.append(make_evidence_relation("ActionItem", matched_node_id, "Regulation", regulation_name, "CONSTRAINED_BY"))

    keyword = constraints.get("keyword")
    for keyword_name in filter_matching_values(row.get("keyword_names"), keyword):
        evidence.append(make_evidence_relation("MeetingItem", item_id, "Keyword", keyword_name, "MENTIONS"))

    return [item for item in evidence if item.get("source_value") and item.get("target_value")]


def make_evidence_relation(source_type, source_value, target_type, target_value, relation: str, target_label=None) -> dict:
    return {
        "source_type": source_type,
        "source_value": source_value,
        "target_type": target_type,
        "target_value": target_value,
        "target_label": target_label or target_value,
        "relation": relation,
    }


def filter_matching_values(values, constraint: str) -> list[str]:
    cleaned = [str(value or "").strip() for value in values or [] if str(value or "").strip()]
    normalized_constraint = str(constraint or "").strip().upper()
    if not normalized_constraint:
        return []
    return [value for value in cleaned if normalized_constraint in value.upper()]


def semantic_target_type_for_relation(relation: str) -> str:
    return {
        "HAS_ACTION": "ActionItem",
        "HAS_DECISION": "Decision",
        "HAS_RISK": "Risk",
        "TRACKS_ISSUE": "Issue",
    }.get(relation, "Entity")


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
        "retrieval_mode": "relation",
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
