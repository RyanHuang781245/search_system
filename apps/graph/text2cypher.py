from __future__ import annotations

import json
import re

from django.conf import settings


ALLOWED_LABELS = {
    "Meeting",
    "MeetingItem",
    "Person",
    "Unit",
    "Keyword",
    "Product",
    "Regulation",
    "Date",
    "ActionItem",
    "Decision",
    "Risk",
    "Issue",
}

ALLOWED_RELATIONSHIPS = {
    "HAS_ITEM",
    "RESPONSIBLE_BY",
    "ATTENDED_BY",
    "CHAIRED_BY",
    "RECORDED_BY",
    "BELONGS_TO_UNIT",
    "HAS_PLANNED_DATE",
    "HAS_COMPLETED_DATE",
    "MENTIONS",
    "MENTIONS_PRODUCT",
    "MENTIONS_REGULATION",
    "CO_OCCURS_WITH",
    "HAS_ACTION",
    "HAS_DECISION",
    "HAS_RISK",
    "TRACKS_ISSUE",
    "FOLLOW_UP_OF",
    "ASSIGNED_TO",
    "TARGETS_PRODUCT",
    "CONSTRAINED_BY",
}

BLOCKED_KEYWORDS = {
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH",
    "REMOVE",
    "DROP",
    "CALL",
    "LOAD",
    "FOREACH",
    "UNWIND",
    "PERIODIC",
    "APOC",
    "DBMS",
    "INDEX",
    "CONSTRAINT",
}

ALLOWED_CLAUSES = {
    "MATCH",
    "OPTIONAL MATCH",
    "WHERE",
    "WITH",
    "RETURN",
    "ORDER BY",
    "LIMIT",
    "SKIP",
    "AND",
    "OR",
}

SCHEMA_CONTEXT = """
Node labels and useful properties:
- Meeting(meeting_id, meeting_name, meeting_date, responsible_unit)
- MeetingItem(item_id, item_no, content, owner, planned_date, actual_completed_date, tracking_result)
- Person(name)
- Unit(name)
- Keyword(name, type, score, method)
- Product(name)
- Regulation(name)
- Date(date_value)
- ActionItem(action_id, title, status)
- Decision(decision_id, title)
- Risk(risk_id, title)
- Issue(issue_id, title, signature)

Core graph patterns:
- (Meeting)-[:HAS_ITEM]->(MeetingItem)
- (MeetingItem)-[:RESPONSIBLE_BY]->(Person)
- (Meeting)-[:ATTENDED_BY|CHAIRED_BY|RECORDED_BY]->(Person)
- (Meeting)-[:BELONGS_TO_UNIT]->(Unit)
- (MeetingItem)-[:HAS_PLANNED_DATE|HAS_COMPLETED_DATE]->(Date)
- (MeetingItem)-[:MENTIONS_PRODUCT]->(Product)
- (MeetingItem)-[:MENTIONS_REGULATION]->(Regulation)
- (MeetingItem)-[:MENTIONS]->(Keyword)
- (MeetingItem)-[:HAS_ACTION]->(ActionItem)
- (MeetingItem)-[:HAS_DECISION]->(Decision)
- (MeetingItem)-[:HAS_RISK]->(Risk)
- (MeetingItem)-[:TRACKS_ISSUE]->(Issue)
- (MeetingItem)-[:FOLLOW_UP_OF]->(MeetingItem)
""".strip()

FEW_SHOT_EXAMPLES = [
    {
        "question": "哪些產品跨最多會議被討論？",
        "cypher": (
            "MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:MENTIONS_PRODUCT]->(product:Product)\n"
            "RETURN product.name AS product, count(DISTINCT meeting) AS meeting_count, count(DISTINCT item) AS item_count\n"
            "ORDER BY meeting_count DESC, item_count DESC"
        ),
    },
    {
        "question": "哪些人負責最多事項？",
        "cypher": (
            "MATCH (item:MeetingItem)-[:RESPONSIBLE_BY]->(person:Person)\n"
            "RETURN person.name AS person, count(DISTINCT item) AS item_count\n"
            "ORDER BY item_count DESC"
        ),
    },
    {
        "question": "哪些會議同時提到 FDA 和 TFDA？",
        "cypher": (
            "MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:MENTIONS_REGULATION]->(regulation:Regulation)\n"
            "WHERE toUpper(regulation.name) IN ['FDA', 'TFDA']\n"
            "WITH meeting, collect(DISTINCT toUpper(regulation.name)) AS regulations\n"
            "WHERE 'FDA' IN regulations AND 'TFDA' IN regulations\n"
            "RETURN meeting.meeting_id AS meeting_id, meeting.meeting_name AS meeting_name, "
            "meeting.meeting_date AS meeting_date, regulations\n"
            "ORDER BY meeting_date DESC"
        ),
    },
    {
        "question": "哪些產品和法規最常一起出現？",
        "cypher": (
            "MATCH (item:MeetingItem)-[:MENTIONS_PRODUCT]->(product:Product)\n"
            "MATCH (item)-[:MENTIONS_REGULATION]->(regulation:Regulation)\n"
            "RETURN product.name AS product, regulation.name AS regulation, count(DISTINCT item) AS item_count\n"
            "ORDER BY item_count DESC"
        ),
    },
]


class Text2CypherError(Exception):
    pass


def explore_text2cypher(client, question: str, limit: int = 20, llm_client=None) -> dict:
    normalized_question = str(question or "").strip()
    max_limit = normalize_limit(limit)
    if not normalized_question:
        raise Text2CypherError("question is required.")
    if not getattr(client, "available", False):
        return {
            "question": normalized_question,
            "cypher": "",
            "rows": [],
            "row_count": 0,
            "graph": empty_text2cypher_graph(),
            "blocked": True,
            "warnings": ["Neo4j is unavailable."],
            "guardrails": guardrail_summary(),
        }

    warnings = []
    template_cypher = template_cypher_for_question(normalized_question)
    if template_cypher:
        cypher = template_cypher
        generated_by = "example_template"
    else:
        generated_by = "llm"
        try:
            raw_response = (llm_client or ollama_text2cypher)(normalized_question, max_limit)
            cypher = extract_cypher(raw_response)
        except Exception as exc:
            return {
                "question": normalized_question,
                "cypher": "",
                "rows": [],
                "row_count": 0,
                "graph": empty_text2cypher_graph(),
                "blocked": True,
                "generated_by": generated_by,
                "warnings": [f"Text2Cypher generation unavailable: {exc}"],
                "guardrails": guardrail_summary(),
            }

    validation = validate_cypher(cypher)
    if not validation["is_valid"]:
        return {
            "question": normalized_question,
            "cypher": cypher,
            "rows": [],
            "row_count": 0,
            "graph": empty_text2cypher_graph(),
            "blocked": True,
            "generated_by": generated_by,
            "warnings": validation["warnings"],
            "guardrails": guardrail_summary(),
        }

    safe_cypher = enforce_limit(cypher, max_limit)
    if safe_cypher != cypher:
        warnings.append(f"LIMIT normalized to {max_limit}.")

    try:
        rows = client.execute_read(_execute_cypher_read, safe_cypher, max_limit) or []
    except Exception as exc:
        return {
            "question": normalized_question,
            "cypher": safe_cypher,
            "rows": [],
            "row_count": 0,
            "graph": empty_text2cypher_graph(),
            "blocked": True,
            "generated_by": generated_by,
            "warnings": [f"Unable to execute generated Cypher: {exc}"],
            "guardrails": guardrail_summary(),
        }

    visible_rows = rows[:max_limit]
    graph = build_text2cypher_graph(visible_rows)
    if getattr(settings, "TEXT2CYPHER_ENABLE_NODE_EXPANSION", False):
        graph, expansion_warnings = expand_text2cypher_graph(client, graph, max_limit)
        warnings.extend(expansion_warnings)
    elif graph_has_isolated_nodes_without_paths(graph):
        warnings.append("Text2Cypher returned nodes without paths; graph only shows explicitly returned nodes.")
    return {
        "question": normalized_question,
        "cypher": safe_cypher,
        "rows": visible_rows,
        "row_count": len(visible_rows),
        "graph": graph,
        "blocked": False,
        "generated_by": generated_by,
        "warnings": warnings,
        "guardrails": guardrail_summary(),
    }


def expand_graph_node(client, node_id: str, limit: int = 10, relation_scope: str = "default") -> dict:
    max_limit = normalize_limit(limit)
    scope = normalize_expansion_scope(relation_scope)
    node_type, value = parse_graph_node_id(node_id)
    if not node_type or not value:
        return {
            "node_id": node_id,
            "graph": empty_text2cypher_graph(),
            "warnings": ["node_id must use '<Type>:<value>' format."],
        }
    if node_type not in TEXT2CYPHER_EXPANDABLE_NODE_TYPES:
        return {
            "node_id": node_id,
            "graph": empty_text2cypher_graph(),
            "warnings": [f"Node type '{node_type}' cannot be expanded."],
        }
    if not getattr(client, "available", False):
        return {
            "node_id": node_id,
            "graph": empty_text2cypher_graph(),
            "warnings": ["Neo4j is unavailable."],
        }

    try:
        rows = client.execute_read(_query_text2cypher_node_expansion, node_type, value, max_limit, scope) or []
    except Exception as exc:
        return {
            "node_id": node_id,
            "node_type": node_type,
            "value": value,
            "graph": empty_text2cypher_graph(),
            "warnings": [f"Unable to expand graph node: {exc}"],
        }
    graph = build_text2cypher_graph(rows[:max_limit])
    summary = graph.setdefault("summary", {})
    summary["projection"] = "manual_node_expansion"
    summary["expanded_from"] = node_id
    summary["relation_scope"] = scope
    summary["node_count"] = len(graph.get("nodes") or [])
    summary["edge_count"] = len(graph.get("edges") or [])
    warnings = []
    if len(rows) >= max_limit:
        warnings.append(f"Expansion limited to {max_limit} relations.")
    if not rows:
        warnings.append("No expandable relationships found for this node.")
    return {
        "node_id": node_id,
        "node_type": node_type,
        "value": value,
        "relation_scope": scope,
        "graph": graph,
        "warnings": warnings,
    }


def parse_graph_node_id(node_id: str) -> tuple[str, str]:
    text = str(node_id or "").strip()
    if ":" not in text:
        return "", ""
    node_type, value = text.split(":", 1)
    return node_type.strip(), value.strip()


def normalize_expansion_scope(scope: str) -> str:
    normalized = str(scope or "default").strip().lower()
    allowed = {
        "default",
        "all",
        "meeting",
        "owner",
        "dates",
        "product_regulation",
        "keyword",
        "semantic",
    }
    return normalized if normalized in allowed else "default"


def ollama_text2cypher(question: str, limit: int) -> str:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    response = requests.post(
        url,
        json={
            "model": settings.OLLAMA_INFERENCE_MODEL,
            "stream": False,
            "messages": [{"role": "user", "content": build_text2cypher_prompt(question, limit)}],
            "options": {"temperature": 0},
        },
        timeout=int(getattr(settings, "TEXT2CYPHER_LLM_TIMEOUT", 12)),
    )
    response.raise_for_status()
    payload = response.json()
    content = (payload.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Ollama Text2Cypher response did not include content.")
    return content


def build_text2cypher_prompt(question: str, limit: int) -> str:
    examples = "\n\n".join(
        f"Question: {example['question']}\nCypher:\n{example['cypher']}"
        for example in FEW_SHOT_EXAMPLES
    )
    return (
        "Generate one read-only Neo4j Cypher query for meeting-record graph exploration.\n"
        "Return JSON only with shape: {\"cypher\":\"...\"}\n"
        "Do not explain. Do not answer the question.\n"
        "Use this enhanced schema context:\n"
        f"{SCHEMA_CONTEXT}\n\n"
        "Allowed clauses: MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT.\n"
        "Never use CREATE, MERGE, SET, DELETE, REMOVE, DROP, CALL, LOAD CSV, APOC, or write operations.\n"
        f"Always include LIMIT {limit} or smaller.\n"
        "Prefer simple retrievals, aggregations, and short graph traversals.\n"
        "For non-aggregation questions, prefer path-first Cypher: MATCH path = (...) RETURN path plus scalar fields.\n"
        "Return the exact path that supports each row so the UI graph can render only the queried relationships.\n"
        "For aggregation questions, return aggregate rows; do not invent graph paths that are not part of the query.\n\n"
        "Few-shot examples:\n"
        f"{examples}\n\n"
        f"Question:\n{question}"
    )


def template_cypher_for_question(question: str) -> str:
    text = str(question or "").strip().lower()
    if has_all(text, ("產品", "最多", "會議")) or has_all(text, ("product", "most", "meeting")):
        return FEW_SHOT_EXAMPLES[0]["cypher"]
    if has_all(text, ("負責", "最多")) or has_all(text, ("responsible", "most")):
        return FEW_SHOT_EXAMPLES[1]["cypher"]
    if ("fda" in text and "tfda" in text and ("同時" in text or "both" in text)):
        return FEW_SHOT_EXAMPLES[2]["cypher"]
    if has_all(text, ("產品", "法規")) or has_all(text, ("product", "regulation")):
        return FEW_SHOT_EXAMPLES[3]["cypher"]
    if ("issue" in text or "問題" in text) and ("沒有" in text or "no " in text) and (
        "follow-up" in text or "follow up" in text or "追蹤" in text
    ):
        return (
            "MATCH (issue:Issue)<-[:TRACKS_ISSUE]-(item:MeetingItem)\n"
            "WITH issue, collect(item) AS items\n"
            "WHERE none(i IN items WHERE EXISTS { MATCH (:MeetingItem)-[:FOLLOW_UP_OF]->(i) })\n"
            "  AND none(i IN items WHERE EXISTS { MATCH (i)-[:FOLLOW_UP_OF]->(:MeetingItem) })\n"
            "RETURN issue.title AS issue, issue.issue_id AS issue_id, size(items) AS item_count\n"
            "ORDER BY item_count DESC"
        )
    product_match = re.search(r"([A-Za-z][A-Za-z0-9_-]*(?:\s+[A-Za-z][A-Za-z0-9_-]*){0,3})", str(question or ""))
    if product_match and ("哪些人" in str(question) or "person" in text or "people" in text):
        product = product_match.group(1).strip().replace("'", "\\'")
        return (
            "MATCH (item:MeetingItem)-[:MENTIONS_PRODUCT]->(product:Product)\n"
            "MATCH (item)-[:RESPONSIBLE_BY]->(person:Person)\n"
            f"WHERE toUpper(product.name) CONTAINS '{product.upper()}'\n"
            "RETURN person.name AS person, product.name AS product, count(DISTINCT item) AS item_count\n"
            "ORDER BY item_count DESC"
        )
    return ""


def has_all(text: str, terms: tuple[str, ...]) -> bool:
    return all(term in text for term in terms)


def extract_cypher(content: str) -> str:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json|cypher)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("cypher"):
            return clean_cypher(payload["cypher"])
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if match:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict) and payload.get("cypher"):
            return clean_cypher(payload["cypher"])
    return clean_cypher(text)


def clean_cypher(cypher: str) -> str:
    text = str(cypher or "").strip()
    text = re.sub(r"^```(?:cypher)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip().rstrip(";").strip()
    return text


def validate_cypher(cypher: str) -> dict:
    warnings = []
    text = clean_cypher(cypher)
    upper = text.upper()
    if not text:
        warnings.append("Generated Cypher is empty.")
    if ";" in text:
        warnings.append("Multiple statements are not allowed.")
    if not re.match(r"^\s*(MATCH|OPTIONAL\s+MATCH|WITH)\b", text, flags=re.I):
        warnings.append("Cypher must start with MATCH, OPTIONAL MATCH, or WITH.")
    for keyword in BLOCKED_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            warnings.append(f"Blocked keyword is not allowed: {keyword}.")
    labels = extract_labels(text)
    relationships = extract_relationship_types(text)
    unknown_labels = sorted(label for label in labels if label not in ALLOWED_LABELS)
    unknown_relationships = sorted(rel for rel in relationships if rel not in ALLOWED_RELATIONSHIPS)
    if unknown_labels:
        warnings.append(f"Unsupported labels: {', '.join(unknown_labels)}.")
    if unknown_relationships:
        warnings.append(f"Unsupported relationships: {', '.join(unknown_relationships)}.")
    if not re.search(r"\bRETURN\b", upper):
        warnings.append("Cypher must include RETURN.")
    return {"is_valid": not warnings, "warnings": warnings}


def extract_labels(cypher: str) -> set[str]:
    labels = set()
    for body in re.findall(r"\(([^)]*)\)", cypher):
        for label in re.findall(r":\s*([A-Za-z][A-Za-z0-9_]*)", body):
            labels.add(label)
    return labels


def extract_relationship_types(cypher: str) -> set[str]:
    relationships = set()
    for body in re.findall(r"\[([^\]]*)\]", cypher):
        for group in re.findall(r":\s*([A-Za-z][A-Za-z0-9_|]*)", body):
            for rel in group.split("|"):
                if rel:
                    relationships.add(rel)
    return relationships


def enforce_limit(cypher: str, limit: int) -> str:
    safe_limit = normalize_limit(limit)
    text = clean_cypher(cypher)
    if re.search(r"\bLIMIT\s+\d+\b", text, flags=re.I):
        return re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {safe_limit}", text, flags=re.I)
    return f"{text}\nLIMIT {safe_limit}"


def normalize_limit(limit) -> int:
    max_limit = int(getattr(settings, "TEXT2CYPHER_MAX_LIMIT", 50))
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 20
    return max(1, min(value, max_limit))


def _execute_cypher_read(tx, cypher: str, limit: int):
    records = tx.run(cypher)
    rows = []
    for record in records:
        rows.append({key: serialize_value(record.get(key)) for key in record.keys()})
        if len(rows) >= limit:
            break
    return rows


def serialize_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_neo4j_path(value):
        return serialize_path_value(value)
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if hasattr(value, "labels") and hasattr(value, "items"):
        return serialize_node_value(value)
    if is_neo4j_relationship(value):
        return serialize_relationship_value(value)
    if hasattr(value, "items"):
        return {str(key): serialize_value(item) for key, item in dict(value).items()}
    return str(value)


def is_neo4j_path(value) -> bool:
    return hasattr(value, "nodes") and hasattr(value, "relationships")


def is_neo4j_relationship(value) -> bool:
    return hasattr(value, "type") and hasattr(value, "items")


def serialize_path_value(value) -> dict:
    nodes = [serialize_node_value(node) for node in list(getattr(value, "nodes", []) or [])]
    relationships = []
    for index, relationship in enumerate(list(getattr(value, "relationships", []) or [])):
        payload = serialize_relationship_value(relationship)
        payload["_source_index"] = index
        payload["_target_index"] = index + 1
        relationships.append(payload)
    return {
        "_type": "Path",
        "nodes": nodes,
        "relationships": relationships,
    }


def serialize_node_value(value) -> dict:
    payload = {str(key): serialize_value(item) for key, item in dict(value).items()}
    payload["_type"] = "Node"
    payload["_labels"] = sorted(str(label) for label in getattr(value, "labels", []))
    payload["_element_id"] = getattr(value, "element_id", None)
    return payload


def serialize_relationship_value(value) -> dict:
    payload = {str(key): serialize_value(item) for key, item in dict(value).items()}
    relationship_type = getattr(value, "type", None)
    if callable(relationship_type):
        relationship_type = relationship_type()
    payload["_type"] = "Relationship"
    payload["_relationship_type"] = str(relationship_type or value.__class__.__name__)
    payload["_element_id"] = getattr(value, "element_id", None)
    return payload


def build_text2cypher_graph(rows: list[dict]) -> dict:
    builder = Text2CypherGraphBuilder()
    for row in rows:
        if not isinstance(row, dict):
            continue
        add_serialized_paths_to_builder(builder, row)
        row = normalize_text2cypher_row(row)
        meeting_id = first_value(row, "meeting_id")
        meeting_label = first_value(row, "meeting_name") or meeting_id
        item_id = first_value(row, "item_id")
        item_label = first_value(row, "item_no") or item_id
        item_title = first_value(row, "content") or item_id

        if meeting_id:
            builder.add_node("Meeting", meeting_id, meeting_label, meeting_label)
        if item_id:
            builder.add_node("MeetingItem", item_id, item_label, item_title)
        if meeting_id and item_id:
            builder.add_edge("Meeting", meeting_id, "MeetingItem", item_id, "HAS_ITEM")

        products = values_for_keys(row, "product", "product_name", "products", "product_names")
        regulations = values_for_keys(row, "regulation", "regulation_name", "regulations", "regulation_names")
        people = values_for_keys(row, "person", "person_name", "people", "owner", "owners", "assignee", "assignees")
        issues = values_for_keys(row, "issue", "issue_id", "issue_title", "issues")
        actions = values_for_keys(row, "action", "action_id", "action_title", "actions")
        decisions = values_for_keys(row, "decision", "decision_id", "decision_title", "decisions")
        risks = values_for_keys(row, "risk", "risk_id", "risk_title", "risks")
        units = values_for_keys(row, "unit", "unit_name", "responsible_unit", "units")
        keywords = values_for_keys(row, "keyword", "keyword_name", "keywords")
        planned_dates = values_for_keys(row, "planned_date", "planned_dates")
        completed_dates = values_for_keys(row, "completed_date", "completed_dates")
        dates = values_for_keys(row, "date", "date_value")

        for product in products:
            builder.add_node("Product", product, product, title_with_row_stats(product, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Product", product, "MENTIONS_PRODUCT")
            elif meeting_id:
                builder.add_edge("Meeting", meeting_id, "Product", product, "MENTIONS_PRODUCT")

        for regulation in regulations:
            builder.add_node("Regulation", regulation, regulation, title_with_row_stats(regulation, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Regulation", regulation, "MENTIONS_REGULATION")
            elif meeting_id:
                builder.add_edge("Meeting", meeting_id, "Regulation", regulation, "MENTIONS_REGULATION")

        for product in products:
            for regulation in regulations:
                builder.add_edge("Product", product, "Regulation", regulation, "CO_MENTIONED_WITH")

        for person in people:
            builder.add_node("Person", person, person, title_with_row_stats(person, row))
            if item_id:
                builder.add_edge(
                    "MeetingItem",
                    item_id,
                    "Person",
                    person,
                    first_value(row, "person_relation", "matched_relation") or "RESPONSIBLE_BY",
                )
            for product in products:
                builder.add_edge("Person", person, "Product", product, "ASSOCIATED_WITH")

        for issue in issues:
            builder.add_node("Issue", issue, issue, title_with_row_stats(issue, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Issue", issue, "TRACKS_ISSUE")

        for action in actions:
            builder.add_node("ActionItem", action, action, title_with_row_stats(action, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "ActionItem", action, "HAS_ACTION")

        for decision in decisions:
            builder.add_node("Decision", decision, decision, title_with_row_stats(decision, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Decision", decision, "HAS_DECISION")

        for risk in risks:
            builder.add_node("Risk", risk, risk, title_with_row_stats(risk, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Risk", risk, "HAS_RISK")

        for unit in units:
            builder.add_node("Unit", unit, unit, title_with_row_stats(unit, row))
            if meeting_id:
                builder.add_edge("Meeting", meeting_id, "Unit", unit, "BELONGS_TO_UNIT")

        for keyword in keywords:
            builder.add_node("Keyword", keyword, keyword, title_with_row_stats(keyword, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Keyword", keyword, "MENTIONS")

        for date in dates:
            builder.add_node("Date", date, date, title_with_row_stats(date, row))
            if item_id:
                builder.add_edge(
                    "MeetingItem",
                    item_id,
                    "Date",
                    date,
                    first_value(row, "date_relation", "matched_relation") or "HAS_DATE",
                )

        for date in planned_dates:
            builder.add_node("Date", date, date, title_with_row_stats(date, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Date", date, "HAS_PLANNED_DATE")

        for date in completed_dates:
            builder.add_node("Date", date, date, title_with_row_stats(date, row))
            if item_id:
                builder.add_edge("MeetingItem", item_id, "Date", date, "HAS_COMPLETED_DATE")

    path_count = count_serialized_paths(rows)
    return {
        "nodes": builder.nodes(),
        "edges": builder.edges(),
        "summary": {
            "node_count": len(builder.nodes()),
            "edge_count": len(builder.edges()),
            "projection": "text2cypher_rows",
            "path_count": path_count,
        },
    }


def expand_text2cypher_graph(client, graph: dict, limit: int) -> tuple[dict, list[str]]:
    """Deterministically expand isolated Text2Cypher nodes into schema-backed graph evidence."""
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    if not nodes:
        return graph, []

    connected_node_ids = {edge.get("source") for edge in edges} | {edge.get("target") for edge in edges}
    isolated_nodes = [node for node in nodes if node.get("id") not in connected_node_ids]
    expandable_nodes = [
        node for node in isolated_nodes if node.get("type") in TEXT2CYPHER_EXPANDABLE_NODE_TYPES
    ]
    if not expandable_nodes:
        return graph, []

    max_limit = normalize_limit(limit)
    per_node_limit = max(1, min(max_limit, int(getattr(settings, "TEXT2CYPHER_EXPANSION_PER_NODE_LIMIT", 10))))
    expanded_rows = []
    warnings = []
    truncated = False

    for node in expandable_nodes[:max_limit]:
        node_type = str(node.get("type") or "").strip()
        value = graph_value_from_node(node)
        if not value:
            continue
        try:
            rows = client.execute_read(_query_text2cypher_node_expansion, node_type, value, per_node_limit) or []
        except Exception as exc:
            warnings.append(f"Unable to expand Text2Cypher graph node {node_type}({value}): {exc}")
            continue
        expanded_rows.extend(rows)
        if len(rows) >= per_node_limit:
            truncated = True

    if not expanded_rows:
        return graph, warnings

    expanded_graph = build_text2cypher_graph(expanded_rows[: max_limit * per_node_limit])
    merged_graph = merge_text2cypher_graphs(graph, expanded_graph)
    summary = merged_graph.setdefault("summary", {})
    summary["projection"] = "text2cypher_rows"
    summary["expansion"] = "deterministic_node_expansion"
    summary["expanded_node_count"] = len(expandable_nodes)
    summary["node_count"] = len(merged_graph.get("nodes") or [])
    summary["edge_count"] = len(merged_graph.get("edges") or [])
    if truncated:
        warnings.append(f"Text2Cypher graph expansion was limited to {per_node_limit} relations per isolated node.")
    return merged_graph, warnings


def graph_has_isolated_nodes_without_paths(graph: dict) -> bool:
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    summary = graph.get("summary") or {}
    return bool(nodes) and not edges and not int(summary.get("path_count") or 0)


TEXT2CYPHER_EXPANDABLE_NODE_TYPES = {
    "Date",
    "Person",
    "Product",
    "Regulation",
    "Keyword",
    "Meeting",
    "MeetingItem",
    "Issue",
    "ActionItem",
    "Decision",
    "Risk",
    "Unit",
}


def _query_text2cypher_node_expansion(tx, node_type: str, value: str, limit: int, relation_scope: str = "default"):
    query = text2cypher_expansion_query(node_type, relation_scope=relation_scope)
    if not query:
        return []
    clean_value = str(value or "").strip()
    records = tx.run(query, value=clean_value, value_upper=clean_value.upper(), limit=limit)
    return [dict(record) for record in records][:limit]


def text2cypher_expansion_query(node_type: str, relation_scope: str = "default") -> str:
    if node_type == "MeetingItem":
        return meeting_item_expansion_query(relation_scope)
    queries = {
        "Date": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[rel:HAS_PLANNED_DATE|HAS_COMPLETED_DATE]->(date:Date)
WHERE coalesce(date.date_value, '') = $value
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       date.date_value AS date_value,
       type(rel) AS date_relation
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Person": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[rel:RESPONSIBLE_BY]->(person:Person)
WHERE toUpper(coalesce(person.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       person.name AS person,
       type(rel) AS person_relation
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Product": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[rel:MENTIONS_PRODUCT]->(product:Product)
WHERE toUpper(coalesce(product.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       product.name AS product
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Regulation": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[rel:MENTIONS_REGULATION]->(regulation:Regulation)
WHERE toUpper(coalesce(regulation.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       regulation.name AS regulation
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Keyword": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[rel:MENTIONS]->(keyword:Keyword)
WHERE toUpper(coalesce(keyword.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       keyword.name AS keyword
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Meeting": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(meeting.meeting_id, '')) = $value_upper
   OR toUpper(coalesce(meeting.meeting_name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content
ORDER BY item_no ASC
LIMIT $limit
""",
        "Issue": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:TRACKS_ISSUE]->(issue:Issue)
WHERE toUpper(coalesce(issue.issue_id, '')) = $value_upper
   OR toUpper(coalesce(issue.title, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       issue.title AS issue
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "ActionItem": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:HAS_ACTION]->(action:ActionItem)
WHERE toUpper(coalesce(action.action_id, '')) = $value_upper
   OR toUpper(coalesce(action.title, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       action.title AS action
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Decision": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:HAS_DECISION]->(decision:Decision)
WHERE toUpper(coalesce(decision.decision_id, '')) = $value_upper
   OR toUpper(coalesce(decision.title, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       decision.title AS decision
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Risk": """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:HAS_RISK]->(risk:Risk)
WHERE toUpper(coalesce(risk.risk_id, '')) = $value_upper
   OR toUpper(coalesce(risk.title, risk.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       coalesce(risk.title, risk.name) AS risk
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
""",
        "Unit": """
MATCH (meeting:Meeting)-[:BELONGS_TO_UNIT]->(unit:Unit)
WHERE toUpper(coalesce(unit.name, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       unit.name AS unit
ORDER BY meeting_date DESC
LIMIT $limit
""",
    }
    return queries.get(node_type, "")


def meeting_item_expansion_query(relation_scope: str = "default") -> str:
    scope = normalize_expansion_scope(relation_scope)
    if scope in {"default", "meeting"}:
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    if scope == "owner":
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:RESPONSIBLE_BY]->(person:Person)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT person.name) AS people
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    if scope == "dates":
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:HAS_PLANNED_DATE]->(planned_date:Date)
OPTIONAL MATCH (item)-[:HAS_COMPLETED_DATE]->(completed_date:Date)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT planned_date.date_value) AS planned_dates,
       collect(DISTINCT completed_date.date_value) AS completed_dates
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    if scope == "product_regulation":
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:MENTIONS_PRODUCT]->(product:Product)
OPTIONAL MATCH (item)-[:MENTIONS_REGULATION]->(regulation:Regulation)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT product.name) AS products,
       collect(DISTINCT regulation.name) AS regulations
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    if scope == "keyword":
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:MENTIONS]->(keyword:Keyword)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT keyword.name) AS keywords
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    if scope == "semantic":
        return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (item)-[:HAS_DECISION]->(decision:Decision)
OPTIONAL MATCH (item)-[:HAS_RISK]->(risk:Risk)
OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT person.name) AS people,
       collect(DISTINCT planned_date.date_value) AS planned_dates,
       collect(DISTINCT completed_date.date_value) AS completed_dates,
       collect(DISTINCT product.name) AS products,
       collect(DISTINCT regulation.name) AS regulations,
       collect(DISTINCT keyword.name) AS keywords,
       collect(DISTINCT action.title) AS actions,
       collect(DISTINCT decision.title) AS decisions,
       collect(DISTINCT coalesce(risk.title, risk.name)) AS risks,
       collect(DISTINCT issue.title) AS issues
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""
    return """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(coalesce(item.item_id, '')) = $value_upper
OPTIONAL MATCH (item)-[:RESPONSIBLE_BY]->(person:Person)
OPTIONAL MATCH (item)-[:HAS_PLANNED_DATE]->(planned_date:Date)
OPTIONAL MATCH (item)-[:HAS_COMPLETED_DATE]->(completed_date:Date)
OPTIONAL MATCH (item)-[:MENTIONS_PRODUCT]->(product:Product)
OPTIONAL MATCH (item)-[:MENTIONS_REGULATION]->(regulation:Regulation)
OPTIONAL MATCH (item)-[:MENTIONS]->(keyword:Keyword)
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (item)-[:HAS_DECISION]->(decision:Decision)
OPTIONAL MATCH (item)-[:HAS_RISK]->(risk:Risk)
OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       collect(DISTINCT person.name) AS people,
       collect(DISTINCT planned_date.date_value) AS planned_dates,
       collect(DISTINCT completed_date.date_value) AS completed_dates,
       collect(DISTINCT product.name) AS products,
       collect(DISTINCT regulation.name) AS regulations,
       collect(DISTINCT keyword.name) AS keywords,
       collect(DISTINCT action.title) AS actions,
       collect(DISTINCT decision.title) AS decisions,
       collect(DISTINCT coalesce(risk.title, risk.name)) AS risks,
       collect(DISTINCT issue.title) AS issues
ORDER BY meeting_date DESC, item_no ASC
LIMIT $limit
"""


def merge_text2cypher_graphs(left: dict, right: dict) -> dict:
    nodes = {}
    edges = {}
    for graph in (left, right):
        for node in graph.get("nodes") or []:
            node_id = node.get("id")
            if node_id:
                nodes.setdefault(node_id, node)
        for edge in graph.get("edges") or []:
            edge_id = edge.get("id")
            if edge_id:
                edges.setdefault(edge_id, edge)
    return {
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
        "summary": dict((left.get("summary") or {}) | (right.get("summary") or {})),
    }


def graph_value_from_node(node: dict) -> str:
    node_id = str(node.get("id") or "")
    if ":" in node_id:
        return node_id.split(":", 1)[1].strip()
    return str(node.get("label") or node.get("title") or "").strip()


def add_serialized_paths_to_builder(builder, row: dict) -> None:
    for path in iter_serialized_paths(row):
        nodes = list(path.get("nodes") or [])
        relationships = list(path.get("relationships") or [])
        for node in nodes:
            identity = serialized_node_identity(node)
            if identity is None:
                continue
            builder.add_node(identity["type"], identity["value"], identity["label"], identity["title"])

        for index, relationship in enumerate(relationships):
            source_index = relationship.get("_source_index", index)
            target_index = relationship.get("_target_index", index + 1)
            if not isinstance(source_index, int) or not isinstance(target_index, int):
                continue
            if source_index < 0 or target_index < 0 or source_index >= len(nodes) or target_index >= len(nodes):
                continue
            source = serialized_node_identity(nodes[source_index])
            target = serialized_node_identity(nodes[target_index])
            relation = str(relationship.get("_relationship_type") or "").strip()
            if source is None or target is None or not relation:
                continue
            builder.add_edge(source["type"], source["value"], target["type"], target["value"], relation)


def iter_serialized_paths(value):
    if isinstance(value, dict):
        if value.get("_type") == "Path":
            yield value
            return
        for item in value.values():
            yield from iter_serialized_paths(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from iter_serialized_paths(item)


def count_serialized_paths(rows: list[dict]) -> int:
    return sum(1 for row in rows if isinstance(row, dict) for _path in iter_serialized_paths(row))


def serialized_node_identity(node: dict) -> dict | None:
    if not isinstance(node, dict):
        return None
    labels = [label for label in node.get("_labels") or [] if label in ALLOWED_LABELS]
    if not labels:
        return None
    node_type = labels[0]
    value = serialized_node_value_for_type(node_type, node)
    if value in (None, ""):
        return None
    label = serialized_node_label_for_type(node_type, node, value)
    title = serialized_node_title_for_type(node_type, node, label)
    return {"type": node_type, "value": value, "label": label, "title": title}


def serialized_node_value_for_type(node_type: str, node: dict):
    keys_by_type = {
        "Meeting": ("meeting_id", "meeting_name"),
        "MeetingItem": ("item_id", "item_no", "content"),
        "Person": ("name",),
        "Unit": ("name",),
        "Keyword": ("name",),
        "Product": ("name",),
        "Regulation": ("name",),
        "Date": ("date_value",),
        "ActionItem": ("action_id", "title"),
        "Decision": ("decision_id", "title"),
        "Risk": ("risk_id", "title", "name"),
        "Issue": ("issue_id", "title", "signature"),
    }
    for key in keys_by_type.get(node_type, ()):
        if node.get(key) not in (None, ""):
            return node.get(key)
    return node.get("_element_id")


def serialized_node_label_for_type(node_type: str, node: dict, fallback):
    keys_by_type = {
        "Meeting": ("meeting_name", "meeting_id"),
        "MeetingItem": ("item_no", "item_id"),
        "Person": ("name",),
        "Unit": ("name",),
        "Keyword": ("name",),
        "Product": ("name",),
        "Regulation": ("name",),
        "Date": ("date_value",),
        "ActionItem": ("title", "action_id"),
        "Decision": ("title", "decision_id"),
        "Risk": ("title", "name", "risk_id"),
        "Issue": ("title", "issue_id"),
    }
    for key in keys_by_type.get(node_type, ()):
        if node.get(key) not in (None, ""):
            return node.get(key)
    return fallback


def serialized_node_title_for_type(node_type: str, node: dict, fallback):
    if node_type == "MeetingItem":
        return node.get("content") or fallback
    if node_type in {"ActionItem", "Decision", "Risk", "Issue"}:
        return node.get("title") or node.get("name") or fallback
    return fallback


def empty_text2cypher_graph() -> dict:
    return {"nodes": [], "edges": [], "summary": {"node_count": 0, "edge_count": 0, "projection": "text2cypher_rows"}}


def normalize_text2cypher_row(row: dict) -> dict:
    normalized = dict(row)
    for value in row.values():
        if not isinstance(value, dict):
            continue
        labels = set(value.get("_labels") or [])
        if "Meeting" in labels:
            normalized.setdefault("meeting_id", value.get("meeting_id"))
            normalized.setdefault("meeting_name", value.get("meeting_name"))
            normalized.setdefault("meeting_date", value.get("meeting_date"))
        if "MeetingItem" in labels:
            normalized.setdefault("item_id", value.get("item_id"))
            normalized.setdefault("item_no", value.get("item_no"))
            normalized.setdefault("content", value.get("content"))
        if "Product" in labels:
            normalized.setdefault("product", value.get("name"))
        if "Regulation" in labels:
            normalized.setdefault("regulation", value.get("name"))
        if "Person" in labels:
            normalized.setdefault("person", value.get("name"))
        if "Date" in labels:
            normalized.setdefault("date_value", value.get("date_value"))
        if "Keyword" in labels:
            normalized.setdefault("keyword", value.get("name"))
        if "Issue" in labels:
            normalized.setdefault("issue", value.get("title") or value.get("issue_id"))
        if "ActionItem" in labels:
            normalized.setdefault("action", value.get("title") or value.get("action_id"))
        if "Decision" in labels:
            normalized.setdefault("decision", value.get("title") or value.get("decision_id"))
        if "Risk" in labels:
            normalized.setdefault("risk", value.get("title") or value.get("name") or value.get("risk_id"))
        if "Unit" in labels:
            normalized.setdefault("unit", value.get("name"))
    return {key: value for key, value in normalized.items() if value not in (None, "")}


class Text2CypherGraphBuilder:
    def __init__(self):
        self._nodes = {}
        self._edges = {}

    def add_node(self, node_type: str, value, label, title) -> None:
        if value is None or value == "":
            return
        node_id = graph_node_id(node_type, value)
        if node_id in self._nodes:
            return
        self._nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": str(label or value),
            "title": str(title or label or value),
        }

    def add_edge(self, source_type: str, source_value, target_type: str, target_value, label: str) -> None:
        if not all([source_type, source_value, target_type, target_value, label]):
            return
        source = graph_node_id(source_type, source_value)
        target = graph_node_id(target_type, target_value)
        edge_id = f"{source}->{label}->{target}"
        if edge_id in self._edges:
            return
        self._edges[edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": label,
            "evidence_source": "text2cypher",
        }

    def nodes(self) -> list[dict]:
        return list(self._nodes.values())

    def edges(self) -> list[dict]:
        return list(self._edges.values())


def graph_node_id(node_type: str, value) -> str:
    return f"{node_type}:{str(value or '').strip()}"


def first_value(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)
        if isinstance(value, (list, tuple, set)):
            value = next((item for item in value if item not in (None, "")), None)
        if value not in (None, ""):
            return value
    return None


def values_for_keys(row: dict, *keys: str) -> list[str]:
    values = []
    for key in keys:
        raw_value = row.get(key)
        if raw_value in (None, ""):
            continue
        raw_values = raw_value if isinstance(raw_value, (list, tuple, set)) else [raw_value]
        for value in raw_values:
            if value in (None, ""):
                continue
            if isinstance(value, dict):
                value = value.get("name") or value.get("title") or value.get("id") or value.get("item_id") or value.get("meeting_id")
            text = str(value).strip()
            if text and text not in values:
                values.append(text)
    return values


def title_with_row_stats(label, row: dict) -> str:
    stats = []
    for key, value in row.items():
        if key.endswith("_count") or key in {"count", "mentions", "item_count", "meeting_count"}:
            stats.append(f"{key}: {value}")
    return f"{label} ({', '.join(stats)})" if stats else str(label)


def guardrail_summary() -> dict:
    return {
        "allowed_labels": sorted(ALLOWED_LABELS),
        "allowed_relationships": sorted(ALLOWED_RELATIONSHIPS),
        "blocked_keywords": sorted(BLOCKED_KEYWORDS),
        "schema_context": SCHEMA_CONTEXT,
        "example_count": len(FEW_SHOT_EXAMPLES),
    }
