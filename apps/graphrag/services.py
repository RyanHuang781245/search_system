from __future__ import annotations

from django.conf import settings

from apps.graph.services import graph_search_query
from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection
from apps.search.ranking import matches_query
from apps.vector.services import VectorServiceError, semantic_search


class GraphRagServiceError(Exception):
    """Raised when GraphRAG answer generation cannot be completed."""


def answer_question(
    question: str,
    limit: int = 5,
    semantic_searcher=None,
    graph_searcher=None,
    llm_client=None,
) -> dict:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise GraphRagServiceError("Question is required.")

    semantic_searcher = semantic_searcher or semantic_search
    graph_searcher = graph_searcher or graph_search_query
    llm_client = llm_client or ollama_answer

    semantic_payload = _safe_semantic_search(semantic_searcher, normalized_question, limit)
    graph_payload = _safe_graph_search(graph_searcher, normalized_question, limit * 4)

    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}
    items_by_id = {item.get("item_id"): item for item in items}

    ranked_item_ids = collect_ranked_item_ids(
        semantic_payload.get("results", []),
        graph_payload.get("results", []),
    )
    structured_context = build_structured_context(ranked_item_ids, items_by_id, meetings_by_id, limit)

    if len(structured_context) < limit:
        structured_context.extend(
            item
            for item in keyword_structured_context(normalized_question, meetings, items, limit)
            if item["item_id"] not in {entry["item_id"] for entry in structured_context}
        )
        structured_context = structured_context[:limit]

    graph_context = build_graph_context(graph_payload.get("results", []), limit=limit * 2)
    semantic_context = semantic_payload.get("results", [])[:limit]
    source_metadata = build_source_metadata(structured_context, semantic_context)

    if not structured_context and not graph_context["paths"] and not semantic_context:
        return {
            "question": normalized_question,
            "answer": "無法由現有會議記錄確認。",
            "contexts": {
                "structured": [],
                "graph": graph_context,
                "semantic": [],
            },
            "sources": [],
            "warnings": semantic_payload.get("warnings", []) + graph_payload.get("warnings", []),
        }

    prompt = build_graphrag_prompt(
        question=normalized_question,
        structured_context=structured_context,
        graph_context=graph_context,
        semantic_context=semantic_context,
        source_metadata=source_metadata,
    )
    answer = llm_client(prompt)

    return {
        "question": normalized_question,
        "answer": answer,
        "contexts": {
            "structured": structured_context,
            "graph": graph_context,
            "semantic": semantic_context,
        },
        "sources": source_metadata,
        "warnings": semantic_payload.get("warnings", []) + graph_payload.get("warnings", []),
    }


def _safe_semantic_search(semantic_searcher, question: str, limit: int) -> dict:
    try:
        return semantic_searcher(question, limit=limit)
    except VectorServiceError as exc:
        return {"query": question, "results": [], "warnings": [str(exc)]}
    except Exception as exc:
        return {"query": question, "results": [], "warnings": [f"Semantic search unavailable: {exc}"]}


def _safe_graph_search(graph_searcher, question: str, limit: int) -> dict:
    try:
        return graph_searcher(question, limit=limit)
    except Exception as exc:
        return {
            "query": question,
            "expanded_keywords": [],
            "results": [],
            "warnings": [f"Graph search unavailable: {exc}"],
        }


def collect_ranked_item_ids(semantic_results: list[dict], graph_results: list[dict]) -> list[str]:
    ranked_ids = []
    seen = set()
    for result in [*graph_results, *semantic_results]:
        item_id = result.get("item_id")
        if item_id and item_id not in seen:
            seen.add(item_id)
            ranked_ids.append(item_id)
    return ranked_ids


def build_structured_context(
    ranked_item_ids: list[str],
    items_by_id: dict,
    meetings_by_id: dict,
    limit: int,
) -> list[dict]:
    context = []
    for item_id in ranked_item_ids:
        item = items_by_id.get(item_id)
        if not item:
            continue
        meeting = meetings_by_id.get(item.get("meeting_id"), {})
        context.append(format_structured_item(meeting, item))
        if len(context) >= limit:
            break
    return context


def keyword_structured_context(question: str, meetings: list[dict], items: list[dict], limit: int) -> list[dict]:
    lowered_query = question.lower()
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}
    matched = []
    for item in items:
        meeting = meetings_by_id.get(item.get("meeting_id"), {})
        fields = [
            meeting.get("meeting_name"),
            meeting.get("responsible_unit"),
            meeting.get("attendees"),
            item.get("content"),
            item.get("owner"),
            item.get("planned_date"),
            item.get("actual_completed_date"),
            item.get("tracking_result"),
        ]
        if any(matches_query(field, lowered_query) for field in fields):
            matched.append(format_structured_item(meeting, item))
        if len(matched) >= limit:
            break
    return matched


def format_structured_item(meeting: dict, item: dict) -> dict:
    return {
        "document_id": item.get("document_id") or meeting.get("document_id"),
        "meeting_id": item.get("meeting_id"),
        "meeting_name": meeting.get("meeting_name"),
        "meeting_date": meeting.get("meeting_date"),
        "responsible_unit": meeting.get("responsible_unit"),
        "item_id": item.get("item_id"),
        "item_no": item.get("item_no"),
        "content": item.get("content"),
        "owner": item.get("owner"),
        "planned_date": item.get("planned_date"),
        "actual_completed_date": item.get("actual_completed_date"),
        "tracking_result": item.get("tracking_result"),
    }


def build_graph_context(graph_results: list[dict], limit: int = 10) -> dict:
    paths = []
    seen = set()
    graph_builder = EvidenceGraphBuilder()
    for result in graph_results:
        path = format_graph_path(result)
        if path in seen:
            continue
        seen.add(path)
        paths.append(
            {
                "meeting_id": result.get("meeting_id"),
                "item_id": result.get("item_id"),
                "matched_keyword": result.get("matched_keyword"),
                "matched_relation": result.get("matched_relation"),
                "matched_entity": result.get("matched_entity"),
                "matched_field": result.get("matched_field"),
                "match_type": result.get("match_type"),
                "intent": result.get("intent"),
                "graph_score": result.get("graph_score"),
                "path": path,
            }
        )
        graph_builder.add_result(result)
        if len(paths) >= limit:
            break
    return {
        "paths": paths,
        "nodes": graph_builder.nodes(),
        "edges": graph_builder.edges(),
    }


class EvidenceGraphBuilder:
    def __init__(self):
        self._nodes = {}
        self._edges = {}

    def add_result(self, result: dict) -> None:
        meeting_id = result.get("meeting_id")
        item_id = result.get("item_id")
        if not meeting_id and not item_id:
            return

        if meeting_id:
            self.add_node(
                node_type="Meeting",
                value=meeting_id,
                label=result.get("meeting_name") or meeting_id,
                title=result.get("meeting_name") or meeting_id,
            )
        if item_id:
            self.add_node(
                node_type="MeetingItem",
                value=item_id,
                label=result.get("item_no") or item_id,
                title=result.get("content") or item_id,
            )
        if meeting_id and item_id:
            self.add_edge("Meeting", meeting_id, "MeetingItem", item_id, "HAS_ITEM")

        evidence_relations = result.get("evidence_relations") or []
        if evidence_relations:
            for evidence_relation in evidence_relations:
                self.add_evidence_relation(evidence_relation)
            return

        relation = result.get("matched_relation") or "MENTIONS"
        if relation == "MENTIONS":
            keyword = result.get("matched_keyword") or result.get("matched_entity")
            if keyword and item_id:
                self.add_node("Keyword", keyword, keyword, keyword)
                self.add_edge("MeetingItem", item_id, "Keyword", keyword, "MENTIONS")
            return

        if relation == "FOLLOW_UP_OF":
            previous_item_id = result.get("matched_node_id") or result.get("matched_entity")
            if previous_item_id and item_id:
                self.add_node("MeetingItem", previous_item_id, previous_item_id, previous_item_id)
                self.add_edge("MeetingItem", item_id, "MeetingItem", previous_item_id, "FOLLOW_UP_OF")
            return

        entity = result.get("matched_entity")
        if not entity:
            return

        entity_type = entity_type_for_relation(relation)
        entity_value = result.get("matched_node_id") or entity
        self.add_node(entity_type, entity_value, entity, entity)
        if relation in {"ATTENDED_BY", "CHAIRED_BY", "RECORDED_BY", "BELONGS_TO_UNIT"} and meeting_id:
            self.add_edge("Meeting", meeting_id, entity_type, entity_value, relation)
        elif item_id:
            self.add_edge("MeetingItem", item_id, entity_type, entity_value, relation)

    def add_evidence_relation(self, evidence_relation: dict) -> None:
        source_type = evidence_relation.get("source_type")
        source_value = evidence_relation.get("source_value")
        target_type = evidence_relation.get("target_type")
        target_value = evidence_relation.get("target_value")
        relation = evidence_relation.get("relation")
        if not all([source_type, source_value, target_type, target_value, relation]):
            return
        self.add_node(source_type, source_value, evidence_relation.get("source_label") or source_value, source_value)
        self.add_node(target_type, target_value, evidence_relation.get("target_label") or target_value, target_value)
        self.add_edge(source_type, source_value, target_type, target_value, relation)

    def add_node(self, node_type: str, value, label, title) -> None:
        node_id = make_graph_node_id(node_type, value)
        if node_id in self._nodes:
            return
        self._nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": str(label or value or node_type),
            "title": str(title or label or value or node_type),
        }

    def add_edge(self, source_type: str, source_value, target_type: str, target_value, label: str) -> None:
        source = make_graph_node_id(source_type, source_value)
        target = make_graph_node_id(target_type, target_value)
        edge_id = f"{source}->{label}->{target}"
        if edge_id in self._edges:
            return
        self._edges[edge_id] = {
            "id": edge_id,
            "source": source,
            "target": target,
            "label": label,
        }

    def nodes(self) -> list[dict]:
        return list(self._nodes.values())

    def edges(self) -> list[dict]:
        return list(self._edges.values())


def make_graph_node_id(node_type: str, value) -> str:
    return f"{node_type}:{str(value or '').strip()}"


def entity_type_for_relation(relation: str) -> str:
    return {
        "RESPONSIBLE_BY": "Person",
        "ATTENDED_BY": "Person",
        "CHAIRED_BY": "Person",
        "RECORDED_BY": "Person",
        "BELONGS_TO_UNIT": "Unit",
        "HAS_PLANNED_DATE": "Date",
        "HAS_COMPLETED_DATE": "Date",
        "MENTIONS_PRODUCT": "Product",
        "MENTIONS_REGULATION": "Regulation",
        "HAS_ACTION": "ActionItem",
        "HAS_DECISION": "Decision",
        "HAS_RISK": "Risk",
        "TRACKS_ISSUE": "Issue",
        "ASSIGNED_TO": "Person",
        "TARGETS_PRODUCT": "Product",
        "CONSTRAINED_BY": "Regulation",
    }.get(relation, "Entity")


def format_graph_path(result: dict) -> str:
    evidence_relations = result.get("evidence_relations") or []
    if evidence_relations:
        meeting_id = result.get("meeting_id") or "unknown_meeting"
        item_id = result.get("item_id") or "unknown_item"
        evidence_paths = [
            (
                f"{relation.get('source_type')}({relation.get('source_value')})"
                f"-[:{relation.get('relation')}]->"
                f"{relation.get('target_type')}({relation.get('target_label') or relation.get('target_value')})"
            )
            for relation in evidence_relations
            if relation.get("source_type") and relation.get("target_type") and relation.get("relation")
        ]
        return "; ".join([f"Meeting({meeting_id})-[:HAS_ITEM]->MeetingItem({item_id})", *evidence_paths])

    relation = result.get("matched_relation")
    if relation and relation != "MENTIONS":
        entity = result.get("matched_entity") or "unknown_entity"
        meeting_id = result.get("meeting_id") or "unknown_meeting"
        item_id = result.get("item_id") or "unknown_item"
        if relation in {"ATTENDED_BY", "CHAIRED_BY", "RECORDED_BY", "BELONGS_TO_UNIT"}:
            return (
                f"Meeting({meeting_id})-[:{relation}]->Entity({entity}); "
                f"Meeting({meeting_id})-[:HAS_ITEM]->MeetingItem({item_id})"
            )
        if relation == "FOLLOW_UP_OF":
            return (
                f"Meeting({meeting_id})-[:HAS_ITEM]->MeetingItem({item_id})"
                f"-[:FOLLOW_UP_OF]->MeetingItem({entity})"
            )
        entity_type = entity_type_for_relation(relation)
        return (
            f"Meeting({meeting_id})-[:HAS_ITEM]->MeetingItem({item_id})"
            f"-[:{relation}]->{entity_type}({entity})"
        )

    field = result.get("matched_field") or "unknown_field"
    keyword = result.get("matched_keyword") or "unknown_keyword"
    meeting_id = result.get("meeting_id") or "unknown_meeting"
    item_id = result.get("item_id") or "unknown_item"
    return (
        f"Keyword({keyword})-[:MENTIONS {{field: {field}}}]-"
        f"MeetingItem({item_id})<-[:HAS_ITEM]-Meeting({meeting_id})"
    )


def build_source_metadata(structured_context: list[dict], semantic_context: list[dict]) -> list[dict]:
    sources = []
    seen = set()
    for entry in [*structured_context, *semantic_context]:
        key = (entry.get("document_id"), entry.get("meeting_id"), entry.get("item_id"))
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "document_id": entry.get("document_id"),
                "meeting_id": entry.get("meeting_id"),
                "item_id": entry.get("item_id"),
                "item_no": entry.get("item_no"),
                "meeting_name": entry.get("meeting_name"),
            }
        )
    return sources


def build_graphrag_prompt(
    question: str,
    structured_context: list[dict],
    graph_context: dict,
    semantic_context: list[dict],
    source_metadata: list[dict],
) -> str:
    return (
        "你是企業會議記錄 GraphRAG 助理。\n"
        "回答規則：\n"
        "1. 只能根據下方 Structured Context、Graph Context、Semantic Context 回答。\n"
        "2. 若資料不足，回答「無法由現有會議記錄確認」。\n"
        "3. 回答需提到可驗證來源，例如 meeting_id、item_id 或 item_no。\n"
        "4. 若引用圖譜關聯，請簡短描述 graph path。\n\n"
        f"Question:\n{question}\n\n"
        f"Structured Context:\n{structured_context}\n\n"
        f"Graph Context:\n{graph_context}\n\n"
        f"Semantic Context:\n{semantic_context}\n\n"
        f"Source Metadata:\n{source_metadata}\n"
    )


def ollama_answer(prompt: str) -> str:
    try:
        import requests
    except Exception as exc:
        raise GraphRagServiceError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    try:
        response = requests.post(
            url,
            json={
                "model": settings.OLLAMA_INFERENCE_MODEL,
                "stream": False,
                "messages": [
                    {
                        "role": "system",
                        "content": "Answer with source-grounded meeting-record facts only.",
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise GraphRagServiceError(f"Unable to generate Ollama answer: {exc}") from exc

    content = (payload.get("message") or {}).get("content")
    if not content:
        raise GraphRagServiceError("Ollama response did not include answer content.")
    return content
