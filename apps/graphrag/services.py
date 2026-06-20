from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
import re

from django.conf import settings

from apps.graph.services import graph_search_query
from apps.graphrag.query_router import QueryRoute, analyze_query_route, route_question
from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection
from apps.search.ranking import matches_query
from apps.vector.services import VectorServiceError, semantic_search


class GraphRagServiceError(Exception):
    """Raised when GraphRAG answer generation cannot be completed."""


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    evidence_source: str
    meeting_id: str | None
    item_id: str | None
    relation: str
    entity: str | None
    confidence: float
    reason: str
    retrieved_by: str
    payload: dict

    def to_dict(self) -> dict:
        return asdict(self)


def answer_question(
    question: str,
    limit: int | str | None = 5,
    semantic_searcher=None,
    graph_searcher=None,
    query_analyzer=None,
    llm_client=None,
    evidence_selector_client=None,
) -> dict:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise GraphRagServiceError("Question is required.")
    query_route = _safe_query_route(query_analyzer or analyze_query_route, normalized_question)
    effective_limit, limit_mode = determine_effective_limit(normalized_question, limit, query_route=query_route)
    graph_limit = graph_search_limit(query_route, effective_limit)

    semantic_searcher = semantic_searcher or semantic_search
    graph_searcher = graph_searcher or graph_search_query
    injected_llm_client = llm_client
    llm_client = llm_client or ollama_answer
    selector_enabled = True
    if evidence_selector_client is None and injected_llm_client is not None:
        selector_enabled = False
    evidence_selector_client = evidence_selector_client or ollama_evidence_selector

    semantic_payload = (
        _safe_semantic_search(semantic_searcher, normalized_question, effective_limit)
        if query_route.use_semantic
        else {"query": normalized_question, "results": [], "warnings": []}
    )
    graph_payload = _safe_graph_search(
        graph_searcher,
        normalized_question,
        graph_limit,
        retrieval_modes=query_route.retrieval_modes,
    )
    authoritative_semantic_item_ids = authoritative_semantic_graph_item_ids(query_route, graph_payload.get("results", []))
    if authoritative_semantic_item_ids:
        semantic_payload = dict(semantic_payload)
        semantic_payload["results"] = [
            result for result in semantic_payload.get("results", []) if result.get("item_id") in authoritative_semantic_item_ids
        ]

    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}
    items_by_id = {item.get("item_id"): item for item in items}

    ranked_item_ids = collect_ranked_item_ids(
        semantic_payload.get("results", []),
        graph_payload.get("results", []),
    )
    structured_context = build_structured_context(ranked_item_ids, items_by_id, meetings_by_id, effective_limit)

    structural_fallback_context = []
    should_use_meeting_items_fallback = query_route.query_type == "structural_list" or is_meeting_summary_route(query_route)
    if should_use_meeting_items_fallback and len(structured_context) < effective_limit:
        structural_fallback_context = [
            item
            for item in meeting_items_structured_context(
                normalized_question,
                meetings,
                items,
                effective_limit,
                meeting_hint=query_route.entities.get("meeting_hint"),
            )
            if item["item_id"] not in {entry["item_id"] for entry in structured_context}
        ]
        structured_context.extend(structural_fallback_context)
        structured_context = structured_context[:effective_limit]

    keyword_fallback_context = []
    allow_keyword_fallback = query_route.allow_keyword_fallback and not authoritative_semantic_item_ids
    if allow_keyword_fallback and len(structured_context) < effective_limit:
        keyword_fallback_context = [
            item
            for item in keyword_structured_context(normalized_question, meetings, items, effective_limit)
            if item["item_id"] not in {entry["item_id"] for entry in structured_context}
        ]
        structured_context.extend(keyword_fallback_context)
        structured_context = structured_context[:effective_limit]

    semantic_context = semantic_payload.get("results", [])[:effective_limit]
    evidence_set = build_answer_evidence_set(
        graph_results=graph_payload.get("results", []),
        structured_context=structured_context,
        semantic_context=semantic_context,
        structural_fallback_context=structural_fallback_context,
        keyword_fallback_context=keyword_fallback_context,
        query_route=query_route,
        graph_limit=effective_limit * 2,
    )
    candidate_evidence_set = evidence_set
    evidence_set, selection_warnings, evidence_selection = select_answer_evidence_set(
        evidence_set=evidence_set,
        question=normalized_question,
        query_route=query_route,
        effective_limit=effective_limit,
        selector_client=evidence_selector_client,
        selector_enabled=selector_enabled,
    )
    structured_context = evidence_set["structured_context"]
    semantic_context = evidence_set["semantic_context"]
    graph_context = evidence_set["graph_context"]
    source_metadata = evidence_set["sources"]
    trace = build_graphrag_trace(
        question=normalized_question,
        query_route=query_route,
        effective_limit=effective_limit,
        limit_mode=limit_mode,
        graph_limit=graph_limit,
        semantic_payload=semantic_payload,
        graph_payload=graph_payload,
        structural_fallback_context=structural_fallback_context,
        keyword_fallback_context=keyword_fallback_context,
        meeting_count=len(meetings),
        item_count=len(items),
        structured_context=structured_context,
        graph_context=graph_context,
        semantic_context=semantic_context,
        source_metadata=source_metadata,
        evidence_set=evidence_set,
        candidate_evidence_set=candidate_evidence_set,
        evidence_selection=evidence_selection,
    )

    if not structured_context and not graph_context["paths"] and not semantic_context:
        trace["is_insufficient"] = True
        return {
            "question": normalized_question,
            "limit": effective_limit,
            "limit_mode": limit_mode,
            "query_route": query_route.to_dict(),
            "trace": trace,
            "answer": "Insufficient meeting-record context to answer.",
            "contexts": {
                "structured": [],
                "graph": graph_context,
                "semantic": [],
            },
            "sources": [],
            "warnings": build_warnings(query_route, semantic_payload, graph_payload),
        }

    prompt = build_graphrag_prompt(
        question=normalized_question,
        query_route=query_route,
        structured_context=structured_context,
        graph_context=graph_context,
        semantic_context=semantic_context,
        source_metadata=source_metadata,
        evidence_records=evidence_set["records"],
    )
    raw_answer = llm_client(prompt)
    parsed_answer_payload = parse_claim_response(raw_answer)
    grounded_answer_text = extract_grounded_answer_text(parsed_answer_payload)
    claims, claim_warnings = build_verified_answer_claims(parsed_answer_payload, evidence_set["records"], query_route)
    if not claims:
        claims = fallback_claims_from_evidence(evidence_set["records"])
    if claims:
        evidence_set = restrict_evidence_set_to_claims(evidence_set, claims, query_route, effective_limit * 2)
        structured_context = evidence_set["structured_context"]
        semantic_context = evidence_set["semantic_context"]
        graph_context = evidence_set["graph_context"]
        source_metadata = evidence_set["sources"]
        if grounded_answer_text and should_use_grounded_answer_text(normalized_question, query_route):
            answer = append_evidence_reference_summary(grounded_answer_text, claims, evidence_set["records"])
        else:
            answer = render_answer_from_claims(claims, evidence_set["records"], query_route=query_route)
        trace = build_graphrag_trace(
            question=normalized_question,
            query_route=query_route,
            effective_limit=effective_limit,
            limit_mode=limit_mode,
            graph_limit=graph_limit,
            semantic_payload=semantic_payload,
            graph_payload=graph_payload,
            structural_fallback_context=structural_fallback_context,
            keyword_fallback_context=keyword_fallback_context,
            meeting_count=len(meetings),
            item_count=len(items),
            structured_context=structured_context,
            graph_context=graph_context,
            semantic_context=semantic_context,
            source_metadata=source_metadata,
            evidence_set=evidence_set,
            candidate_evidence_set=candidate_evidence_set,
            evidence_selection=evidence_selection,
        )
        trace["answer_claims"] = {
            "count": len(claims),
            "evidence_ids": sorted({evidence_id for claim in claims for evidence_id in claim.get("evidence_ids", [])}),
        }
    else:
        answer = raw_answer

    return {
        "question": normalized_question,
        "limit": effective_limit,
        "limit_mode": limit_mode,
        "query_route": query_route.to_dict(),
        "trace": trace,
        "answer": answer,
        "contexts": {
            "structured": structured_context,
            "graph": graph_context,
            "semantic": semantic_context,
        },
        "sources": source_metadata,
        "warnings": build_warnings(query_route, semantic_payload, graph_payload) + selection_warnings + claim_warnings,
    }


def determine_effective_limit(question: str, requested_limit=None, query_route: QueryRoute | None = None) -> tuple[int, str]:
    value = str(requested_limit if requested_limit is not None else "auto").strip().lower()
    fixed_modes = {
        "focused": (5, "focused"),
        "precision": (5, "focused"),
        "balanced": (8, "balanced"),
        "explore": (8, "balanced"),
        "exploratory": (8, "balanced"),
        "broad": (12, "broad"),
        "inventory": (12, "broad"),
        "wide": (12, "broad"),
    }
    if value in fixed_modes:
        return fixed_modes[value]
    if value and value != "auto":
        try:
            return max(min(int(value), 20), 1), "manual"
        except ValueError:
            return auto_limit_for_question(question, query_route=query_route)
    return auto_limit_for_question(question, query_route=query_route)


def auto_limit_for_question(question: str, query_route: QueryRoute | None = None) -> tuple[int, str]:
    if query_route is None:
        query_route = route_question(question)
    return query_route.default_limit, query_route.limit_mode


def _safe_semantic_search(semantic_searcher, question: str, limit: int) -> dict:
    try:
        return semantic_searcher(question, limit=limit)
    except VectorServiceError as exc:
        return {"query": question, "results": [], "warnings": [str(exc)]}
    except Exception as exc:
        return {"query": question, "results": [], "warnings": [f"Semantic search unavailable: {exc}"]}


def _safe_query_route(query_analyzer, question: str) -> QueryRoute:
    try:
        route = query_analyzer(question)
    except Exception as exc:
        fallback = route_question(question)
        return QueryRoute(
            query_type=fallback.query_type,
            retrieval_modes=fallback.retrieval_modes,
            use_semantic=fallback.use_semantic,
            allow_keyword_fallback=fallback.allow_keyword_fallback,
            default_limit=fallback.default_limit,
            limit_mode=fallback.limit_mode,
            answer_style=fallback.answer_style,
            confidence=fallback.confidence,
            route_source="heuristic_fallback",
            entities=fallback.entities,
            warnings=(f"Query analyzer unavailable: {exc}",),
        )
    if isinstance(route, QueryRoute):
        return route
    fallback = route_question(question)
    return QueryRoute(
        query_type=fallback.query_type,
        retrieval_modes=fallback.retrieval_modes,
        use_semantic=fallback.use_semantic,
        allow_keyword_fallback=fallback.allow_keyword_fallback,
        default_limit=fallback.default_limit,
        limit_mode=fallback.limit_mode,
        answer_style=fallback.answer_style,
        confidence=fallback.confidence,
        route_source="heuristic_fallback",
        entities=fallback.entities,
        warnings=("Query analyzer returned an invalid route.",),
    )


def build_warnings(query_route: QueryRoute, semantic_payload: dict, graph_payload: dict) -> list[str]:
    return [
        *list(query_route.warnings or []),
        *list(semantic_payload.get("warnings", []) or []),
        *list(graph_payload.get("warnings", []) or []),
    ]


def _safe_graph_search(graph_searcher, question: str, limit: int, retrieval_modes=None) -> dict:
    try:
        try:
            return graph_searcher(question, limit=limit, retrieval_modes=retrieval_modes)
        except TypeError as exc:
            if "retrieval_modes" not in str(exc):
                raise
            return graph_searcher(question, limit=limit)
    except Exception as exc:
        return {
            "query": question,
            "expanded_keywords": [],
            "results": [],
            "warnings": [f"Graph search unavailable: {exc}"],
        }


def graph_search_limit(query_route: QueryRoute, effective_limit: int) -> int:
    if query_route.query_type in {"structural_list", "relation_lookup", "composite_query", "follow_up_tracking"}:
        return effective_limit
    return effective_limit * 4


def authoritative_semantic_graph_item_ids(query_route: QueryRoute, graph_results: list[dict]) -> set[str]:
    if query_route.query_type not in {"semantic_summary", "follow_up_tracking"}:
        return set()
    semantic_relations = {"HAS_RISK", "HAS_DECISION", "TRACKS_ISSUE", "FOLLOW_UP_OF"}
    return {
        str(result.get("item_id"))
        for result in graph_results
        if result.get("item_id") and result.get("matched_relation") in semantic_relations
    }


def is_meeting_summary_route(query_route: QueryRoute) -> bool:
    return query_route.query_type == "meeting_summary"


def build_graphrag_trace(
    *,
    question: str,
    query_route: QueryRoute,
    effective_limit: int,
    limit_mode: str,
    graph_limit: int,
    semantic_payload: dict,
    graph_payload: dict,
    structural_fallback_context: list[dict],
    keyword_fallback_context: list[dict],
    meeting_count: int,
    item_count: int,
    structured_context: list[dict],
    graph_context: dict,
    semantic_context: list[dict],
    source_metadata: list[dict],
    evidence_set: dict | None = None,
    candidate_evidence_set: dict | None = None,
    evidence_selection: dict | None = None,
) -> dict:
    semantic_results = semantic_payload.get("results", [])
    graph_results = graph_payload.get("results", [])
    evidence_records = (evidence_set or {}).get("records", [])
    candidate_records = (candidate_evidence_set or evidence_set or {}).get("records", [])
    evidence_sources = Counter(record.get("evidence_source") for record in evidence_records)
    evidence_relations = Counter(record.get("relation") for record in evidence_records)
    selection_payload = evidence_selection or {
        "mode": "not_applied",
        "candidate_count": len(candidate_records),
        "selected_count": len(evidence_records),
        "selected_evidence_ids": [record.get("evidence_id") for record in evidence_records if record.get("evidence_id")],
    }
    return {
        "question": question,
        "route": query_route.to_dict(),
        "limit": effective_limit,
        "limit_mode": limit_mode,
        "retrievers": [
            {
                "name": "semantic",
                "enabled": bool(query_route.use_semantic),
                "limit": effective_limit if query_route.use_semantic else 0,
                "count": len(semantic_results),
                "warnings": semantic_payload.get("warnings", []),
            },
            {
                "name": "graph",
                "enabled": True,
                "limit": graph_limit,
                "retrieval_modes": list(query_route.retrieval_modes),
                "count": len(graph_results),
                "expanded_keywords": graph_payload.get("expanded_keywords", []),
                "warnings": graph_payload.get("warnings", []),
            },
            {
                "name": "mongo_structural_fallback",
                "enabled": query_route.query_type == "structural_list" or is_meeting_summary_route(query_route),
                "limit": effective_limit if query_route.query_type == "structural_list" or is_meeting_summary_route(query_route) else 0,
                "count": len(structural_fallback_context),
            },
            {
                "name": "mongo_keyword_fallback",
                "enabled": bool(query_route.allow_keyword_fallback and not authoritative_semantic_graph_item_ids(query_route, graph_results)),
                "limit": effective_limit if query_route.allow_keyword_fallback and not authoritative_semantic_graph_item_ids(query_route, graph_results) else 0,
                "count": len(keyword_fallback_context),
            },
        ],
        "corpus_counts": {
            "meetings": meeting_count,
            "items": item_count,
        },
        "context_counts": {
            "structured": len(structured_context),
            "graph_paths": len(graph_context.get("paths", [])),
            "semantic": len(semantic_context),
            "sources": len(source_metadata),
            "evidence": len(evidence_records),
            "candidate_evidence": len(candidate_records),
        },
        "evidence": {
            "count": len(evidence_records),
            "candidate_count": len(candidate_records),
            "sources": {key: value for key, value in evidence_sources.items() if key},
            "relations": {key: value for key, value in evidence_relations.items() if key},
            "selection": selection_payload,
        },
        "graph_summary": graph_context.get("summary", {}),
        "is_insufficient": False,
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


def build_answer_evidence_set(
    *,
    graph_results: list[dict],
    structured_context: list[dict],
    semantic_context: list[dict],
    structural_fallback_context: list[dict],
    keyword_fallback_context: list[dict],
    query_route: QueryRoute,
    graph_limit: int,
) -> dict:
    graph_evidence_results = augment_graph_results_with_structured_context(
        graph_results,
        structured_context,
        semantic_context,
        structural_fallback_context,
        keyword_fallback_context,
    )
    represented_item_ids = {result.get("item_id") for result in graph_evidence_results if result.get("item_id")}
    for item in semantic_context:
        item_id = item.get("item_id")
        if not item_id or item_id in represented_item_ids:
            continue
        represented_item_ids.add(item_id)
        graph_evidence_results.append(semantic_item_graph_result(item))

    graph_evidence_results, records = build_evidence_records(graph_evidence_results)
    graph_context = build_graph_context(graph_evidence_results, limit=graph_limit, query_route=query_route)
    return {
        "records": records,
        "structured_context": structured_context,
        "semantic_context": semantic_context,
        "graph_results": graph_evidence_results,
        "graph_context": graph_context,
        "sources": build_source_metadata_from_evidence(records),
    }


def select_answer_evidence_set(
    *,
    evidence_set: dict,
    question: str,
    query_route: QueryRoute,
    effective_limit: int,
    selector_client=None,
    selector_enabled: bool = True,
) -> tuple[dict, list[str], dict]:
    records = evidence_set.get("records", [])
    candidate_ids = [record.get("evidence_id") for record in records if record.get("evidence_id")]
    if not records:
        return evidence_set, [], evidence_selection_trace("empty", candidate_ids, [], "no evidence")
    if not should_use_llm_evidence_selector(query_route):
        return evidence_set, [], evidence_selection_trace(
            "complete_route",
            candidate_ids,
            candidate_ids,
            f"{query_route.query_type} keeps complete retrieved evidence",
        )
    if not selector_enabled:
        return evidence_set, [], evidence_selection_trace(
            "disabled_injected_llm",
            candidate_ids,
            candidate_ids,
            "selector disabled because answer llm client was injected",
        )
    if not getattr(settings, "GRAPHRAG_EVIDENCE_SELECTOR_ENABLED", True):
        return evidence_set, [], evidence_selection_trace("disabled", candidate_ids, candidate_ids, "selector disabled")

    selector_client = selector_client or ollama_evidence_selector
    try:
        raw_selection = selector_client(build_evidence_selector_prompt(question, query_route, records, effective_limit))
        selected_ids, reason = parse_evidence_selection(raw_selection, records)
    except Exception as exc:
        return evidence_set, [f"Evidence selector unavailable: {exc}"], evidence_selection_trace(
            "fallback_all",
            candidate_ids,
            candidate_ids,
            "selector failed; kept all candidate evidence",
        )
    if not selected_ids:
        return evidence_set, ["Evidence selector returned no valid evidence; kept all candidates."], evidence_selection_trace(
            "fallback_all",
            candidate_ids,
            candidate_ids,
            "selector returned no valid evidence",
        )
    selected_set = restrict_evidence_set_to_evidence_ids(evidence_set, set(selected_ids), query_route, effective_limit * 2)
    return selected_set, [], evidence_selection_trace("llm", candidate_ids, selected_ids, reason)


def should_use_llm_evidence_selector(query_route: QueryRoute) -> bool:
    return query_route.query_type in {"meeting_summary", "semantic_summary", "keyword_exploration", "open_qa", "composite_query"}


def evidence_selection_trace(mode: str, candidate_ids: list[str], selected_ids: list[str], reason: str) -> dict:
    return {
        "mode": mode,
        "candidate_count": len(candidate_ids),
        "selected_count": len(selected_ids),
        "candidate_evidence_ids": list(candidate_ids),
        "selected_evidence_ids": list(selected_ids),
        "reason": reason,
    }


def build_evidence_selector_prompt(question: str, query_route: QueryRoute, evidence_records: list[dict], effective_limit: int) -> str:
    compact_records = [compact_evidence_record_for_llm(record) for record in evidence_records]
    return (
        "You are the evidence selector for a meeting-record GraphRAG system.\n"
        "Select only evidence records that are directly useful for answering the user question.\n"
        "Do not answer the question. Do not invent evidence ids.\n"
        "Return JSON only with this exact shape:\n"
        '{"selected_evidence_ids":["evidence_001"],"reason":"short reason"}\n'
        "Selection rules:\n"
        "- Prefer precise relation/path evidence over generic keyword evidence.\n"
        "- For summaries, choose evidence that supports the main themes, not unrelated mentions.\n"
        "- For exact filtered questions, keep every record that satisfies the filter.\n"
        f"- Select at most {max(effective_limit, 1)} evidence records unless all candidates are clearly needed.\n\n"
        f"Question:\n{question}\n\n"
        f"Query route:\n{query_route.to_dict()}\n\n"
        f"Candidate evidence records:\n{json.dumps(compact_records, ensure_ascii=False, default=str)}"
    )


def compact_evidence_record_for_llm(record: dict) -> dict:
    payload = record.get("payload") or {}
    return {
        "evidence_id": record.get("evidence_id"),
        "source": record.get("evidence_source"),
        "retriever": record.get("retrieved_by"),
        "relation": record.get("relation"),
        "entity": record.get("entity"),
        "meeting_id": record.get("meeting_id"),
        "meeting_name": payload.get("meeting_name"),
        "meeting_date": payload.get("meeting_date"),
        "item_id": record.get("item_id"),
        "item_no": payload.get("item_no"),
        "content": payload.get("content"),
        "owner": payload.get("owner"),
        "planned_date": payload.get("planned_date"),
        "actual_completed_date": payload.get("actual_completed_date"),
        "tracking_result": payload.get("tracking_result"),
        "matched_field": payload.get("matched_field"),
        "matched_keyword": payload.get("matched_keyword"),
        "score": record.get("confidence"),
    }


def parse_evidence_selection(raw_selection: str, evidence_records: list[dict]) -> tuple[list[str], str]:
    payload = parse_claim_response(raw_selection)
    if not isinstance(payload, dict):
        raise ValueError("Evidence selector response was not valid JSON.")
    valid_ids = [record.get("evidence_id") for record in evidence_records if record.get("evidence_id")]
    valid_id_set = set(valid_ids)
    selected = []
    for evidence_id in payload.get("selected_evidence_ids") or payload.get("evidence_ids") or []:
        evidence_id = str(evidence_id or "").strip()
        if evidence_id in valid_id_set and evidence_id not in selected:
            selected.append(evidence_id)
    return selected, str(payload.get("reason") or "").strip()


def restrict_evidence_set_to_evidence_ids(
    evidence_set: dict,
    evidence_ids: set[str],
    query_route: QueryRoute,
    graph_limit: int,
) -> dict:
    if not evidence_ids:
        return evidence_set
    records = [record for record in evidence_set["records"] if record.get("evidence_id") in evidence_ids]
    graph_results = [
        result
        for result in evidence_set["graph_results"]
        if result.get("evidence_id") in evidence_ids
    ]
    item_ids = {record.get("item_id") for record in records if record.get("item_id")}
    return {
        "records": records,
        "structured_context": filter_context_by_item_ids(evidence_set["structured_context"], item_ids),
        "semantic_context": filter_context_by_item_ids(evidence_set["semantic_context"], item_ids),
        "graph_results": graph_results,
        "graph_context": build_graph_context(graph_results, limit=graph_limit, query_route=query_route, force_complete=True),
        "sources": build_source_metadata_from_evidence(records),
    }


def build_evidence_records(graph_evidence_results: list[dict]) -> tuple[list[dict], list[dict]]:
    records = []
    annotated_results = []
    seen = set()
    for index, result in enumerate(graph_evidence_results, start=1):
        relation = result.get("matched_relation") or "HAS_ITEM"
        key = (
            result.get("meeting_id"),
            result.get("item_id"),
            relation,
            result.get("matched_entity"),
            result.get("evidence_source") or "neo4j",
        )
        if key in seen:
            continue
        seen.add(key)
        annotated_result = dict(result)
        annotated_result["evidence_id"] = f"evidence_{len(records) + 1:03d}"
        annotated_results.append(annotated_result)
        records.append(
            EvidenceRecord(
                evidence_id=annotated_result["evidence_id"],
                evidence_source=annotated_result.get("evidence_source") or "neo4j",
                meeting_id=annotated_result.get("meeting_id"),
                item_id=annotated_result.get("item_id"),
                relation=relation,
                entity=annotated_result.get("matched_entity") or annotated_result.get("matched_keyword"),
                confidence=float(annotated_result.get("graph_score") or 0),
                reason=annotated_result.get("match_type") or annotated_result.get("matched_field") or "retrieved evidence",
                retrieved_by=annotated_result.get("retrieval_mode") or annotated_result.get("intent") or "unknown",
                payload=annotated_result,
            ).to_dict()
        )
    return annotated_results, records


def build_verified_answer_claims(
    raw_answer,
    evidence_records: list[dict],
    query_route: QueryRoute,
) -> tuple[list[dict], list[str]]:
    warnings = []
    payload = raw_answer if isinstance(raw_answer, (dict, list)) else parse_claim_response(raw_answer)
    claims = normalize_answer_claims(payload, evidence_records)
    claims = complete_claims_with_evidence(claims, evidence_records, query_route)
    return claims, warnings


def parse_claim_response(raw_answer: str):
    text = str(raw_answer or "").strip()
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def normalize_answer_claims(payload, evidence_records: list[dict]) -> list[dict]:
    if payload is None:
        return []
    valid_evidence_ids = {record.get("evidence_id") for record in evidence_records}
    raw_claims = payload.get("claims") if isinstance(payload, dict) else payload
    if not isinstance(raw_claims, list):
        return []
    claims = []
    seen = set()
    for raw_claim in raw_claims:
        if not isinstance(raw_claim, dict):
            continue
        claim_text = str(raw_claim.get("claim") or raw_claim.get("text") or "").strip()
        evidence_ids = [
            str(evidence_id).strip()
            for evidence_id in raw_claim.get("evidence_ids", [])
            if str(evidence_id).strip() in valid_evidence_ids
        ]
        if not claim_text or not evidence_ids:
            continue
        key = (claim_text, tuple(evidence_ids))
        if key in seen:
            continue
        seen.add(key)
        claims.append({"claim": claim_text, "evidence_ids": evidence_ids})
    return claims


def extract_grounded_answer_text(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    answer = str(payload.get("answer") or payload.get("summary") or "").strip()
    return answer


def should_use_grounded_answer_text(question: str, query_route: QueryRoute) -> bool:
    if query_route.query_type in {"meeting_summary", "semantic_summary"}:
        return True
    text = str(question or "").lower()
    summary_markers = (
        "摘要",
        "整理",
        "統整",
        "總結",
        "重點",
        "說明",
        "分析",
        "summary",
        "summarize",
        "overview",
    )
    return any(marker in text for marker in summary_markers)


def complete_claims_with_evidence(
    claims: list[dict],
    evidence_records: list[dict],
    query_route: QueryRoute,
) -> list[dict]:
    if query_route.query_type not in {"structural_list", "relation_lookup", "composite_query", "follow_up_tracking"}:
        return claims
    claimed_evidence_ids = {evidence_id for claim in claims for evidence_id in claim.get("evidence_ids", [])}
    completed = list(claims)
    for record in evidence_records:
        evidence_id = record.get("evidence_id")
        if evidence_id in claimed_evidence_ids:
            continue
        completed.append({"claim": claim_text_from_evidence(record), "evidence_ids": [evidence_id]})
    return completed


def fallback_claims_from_evidence(evidence_records: list[dict]) -> list[dict]:
    return [
        {"claim": claim_text_from_evidence(record), "evidence_ids": [record.get("evidence_id")]}
        for record in evidence_records
        if record.get("evidence_id")
    ]


def claim_text_from_evidence(record: dict) -> str:
    payload = record.get("payload") or {}
    relation = record.get("relation") or payload.get("matched_relation") or "HAS_ITEM"
    entity = record.get("entity") or payload.get("matched_entity")
    content = str(payload.get("content") or "").strip()
    item_no = payload.get("item_no")
    item_prefix = f"item_no {item_no}: " if item_no else ""
    if relation == "HAS_PLANNED_DATE":
        return f"預計日期 {entity}，{item_prefix}{content}"
    if relation == "HAS_COMPLETED_DATE":
        return f"完成日期 {entity}，{item_prefix}{content}"
    if relation == "RESPONSIBLE_BY":
        return f"{entity} 負責，{item_prefix}{content}"
    if relation == "TRACKS_ISSUE":
        sequence = payload.get("sequence_no")
        sequence_prefix = f"追蹤序 {sequence}，" if sequence else ""
        issue = entity or payload.get("issue_title") or payload.get("issue_id")
        return f"{issue}：{sequence_prefix}{item_prefix}{content}"
    if relation == "FOLLOW_UP_OF":
        previous_item_id = payload.get("previous_item_id") or payload.get("matched_node_id")
        return f"後續追蹤 {previous_item_id}，{item_prefix}{content}"
    if relation == "HAS_ITEM":
        return f"{item_prefix}{content}"
    if entity:
        return f"{relation} {entity}，{item_prefix}{content}"
    return f"{item_prefix}{content}"


def render_answer_from_claims(claims: list[dict], evidence_records: list[dict], query_route: QueryRoute | None = None) -> str:
    if query_route and query_route.query_type in {"meeting_summary", "semantic_summary"}:
        return render_summary_answer_from_claims(claims, evidence_records)
    evidence_by_id = {record.get("evidence_id"): record for record in evidence_records}
    lines = ["根據會議記錄，相關事項如下：", ""]
    for index, claim in enumerate(claims, start=1):
        source_labels = [
            source_label_for_evidence(evidence_by_id[evidence_id])
            for evidence_id in claim.get("evidence_ids", [])
            if evidence_id in evidence_by_id
        ]
        source_text = "；".join(source_labels)
        suffix = f"（來源：{source_text}）" if source_text else ""
        lines.append(f"{index}. {claim.get('claim')}{suffix}")
    return "\n".join(lines)


def render_summary_answer_from_claims(claims: list[dict], evidence_records: list[dict]) -> str:
    if not claims:
        return "無法由現有會議記錄整理摘要。"
    evidence_by_id = {record.get("evidence_id"): record for record in evidence_records}
    meeting_names = []
    for claim in claims:
        for evidence_id in claim.get("evidence_ids", []):
            record = evidence_by_id.get(evidence_id) or {}
            payload = record.get("payload") or {}
            meeting_name = payload.get("meeting_name")
            if meeting_name and meeting_name not in meeting_names:
                meeting_names.append(meeting_name)
    intro = "根據會議記錄，"
    if meeting_names:
        intro = f"根據 {'、'.join(meeting_names[:3])} 的會議記錄，"
    claim_texts = [str(claim.get("claim") or "").strip().rstrip("。") for claim in claims if str(claim.get("claim") or "").strip()]
    if not claim_texts:
        return "無法由現有會議記錄整理摘要。"
    if len(claim_texts) == 1:
        return append_evidence_reference_summary(f"{intro}{claim_texts[0]}。", claims, evidence_records)
    body = "；".join(claim_texts[:5])
    if len(claim_texts) > 5:
        body += f"；另有 {len(claim_texts) - 5} 項相關紀錄可作為補充"
    return append_evidence_reference_summary(f"{intro}重點可整理為：{body}。", claims, evidence_records)


def append_evidence_reference_summary(answer: str, claims: list[dict], evidence_records: list[dict]) -> str:
    reference_text = evidence_reference_summary(claims, evidence_records)
    if not reference_text:
        return answer
    if reference_text in answer:
        return answer
    return f"{answer}\n\n依據：{reference_text}"


def evidence_reference_summary(claims: list[dict], evidence_records: list[dict]) -> str:
    evidence_by_id = {record.get("evidence_id"): record for record in evidence_records}
    references = []
    seen = set()
    for claim in claims:
        for evidence_id in claim.get("evidence_ids", []):
            record = evidence_by_id.get(evidence_id) or {}
            meeting_id = record.get("meeting_id")
            item_id = record.get("item_id")
            if not meeting_id and not item_id:
                continue
            label = f"{meeting_id or 'unknown_meeting'} / {item_id or 'unknown_item'}"
            if label in seen:
                continue
            seen.add(label)
            references.append(label)
    return "；".join(references)


def source_label_for_evidence(record: dict) -> str:
    payload = record.get("payload") or {}
    meeting_id = record.get("meeting_id") or "unknown_meeting"
    item_id = record.get("item_id") or "unknown_item"
    item_no = payload.get("item_no")
    evidence_id = record.get("evidence_id")
    if item_no:
        return f"{meeting_id} / {item_id} / item_no {item_no} / {evidence_id}"
    return f"{meeting_id} / {item_id} / {evidence_id}"


def restrict_evidence_set_to_claims(
    evidence_set: dict,
    claims: list[dict],
    query_route: QueryRoute,
    graph_limit: int,
) -> dict:
    used_evidence_ids = {evidence_id for claim in claims for evidence_id in claim.get("evidence_ids", [])}
    if not used_evidence_ids:
        return evidence_set
    return restrict_evidence_set_to_evidence_ids(evidence_set, used_evidence_ids, query_route, graph_limit)


def filter_context_by_item_ids(context: list[dict], item_ids: set[str]) -> list[dict]:
    if not item_ids:
        return context
    return [item for item in context if item.get("item_id") in item_ids]


def augment_graph_results_with_structured_context(
    graph_results: list[dict],
    structured_context: list[dict],
    semantic_results: list[dict],
    structural_fallback_context: list[dict],
    keyword_fallback_context: list[dict],
) -> list[dict]:
    answer_item_ids, answer_meeting_ids = answer_context_keys(structured_context, semantic_results)
    structured_by_item_id = {item["item_id"]: item for item in structured_context if item.get("item_id")}
    aligned_graph_results = [
        merge_structured_metadata(result, structured_by_item_id)
        for result in graph_results
        if graph_result_matches_answer_context(result, answer_item_ids, answer_meeting_ids)
    ]
    augmented = [
        dict(result, evidence_source=result.get("evidence_source") or "neo4j")
        for result in aligned_graph_results
    ]
    represented_item_ids = {result.get("item_id") for result in augmented if result.get("item_id")}
    source_by_item_id = structured_evidence_sources(
        semantic_results=semantic_results,
        structural_fallback_context=structural_fallback_context,
        keyword_fallback_context=keyword_fallback_context,
    )
    for item in structured_context:
        item_id = item.get("item_id")
        if not item_id or item_id in represented_item_ids:
            continue
        represented_item_ids.add(item_id)
        augmented.append(structured_item_graph_result(item, source_by_item_id.get(item_id, "structured_context")))
    return augmented


def merge_structured_metadata(result: dict, structured_by_item_id: dict) -> dict:
    item_id = result.get("item_id")
    structured_item = structured_by_item_id.get(item_id) if item_id else None
    if not structured_item:
        return result
    merged = dict(result)
    for key in (
        "document_id",
        "meeting_id",
        "meeting_name",
        "meeting_date",
        "item_id",
        "item_no",
        "content",
        "owner",
        "planned_date",
        "actual_completed_date",
        "tracking_result",
    ):
        if not merged.get(key) and structured_item.get(key):
            merged[key] = structured_item.get(key)
    return merged


def answer_context_keys(structured_context: list[dict], semantic_results: list[dict]) -> tuple[set[str], set[str]]:
    item_ids = {
        item["item_id"]
        for item in [*structured_context, *semantic_results]
        if item.get("item_id")
    }
    meeting_ids = {
        item["meeting_id"]
        for item in [*structured_context, *semantic_results]
        if item.get("meeting_id")
    }
    return item_ids, meeting_ids


def graph_result_matches_answer_context(
    result: dict,
    answer_item_ids: set[str],
    answer_meeting_ids: set[str],
) -> bool:
    if not answer_item_ids and not answer_meeting_ids:
        return True
    item_id = result.get("item_id")
    if item_id:
        return item_id in answer_item_ids
    meeting_id = result.get("meeting_id")
    return bool(meeting_id and meeting_id in answer_meeting_ids)


def structured_evidence_sources(
    *,
    semantic_results: list[dict],
    structural_fallback_context: list[dict],
    keyword_fallback_context: list[dict],
) -> dict:
    source_by_item_id = {}
    for result in semantic_results:
        if result.get("item_id"):
            source_by_item_id[result["item_id"]] = "semantic_context"
    for result in keyword_fallback_context:
        if result.get("item_id"):
            source_by_item_id[result["item_id"]] = "mongo_keyword_fallback"
    for result in structural_fallback_context:
        if result.get("item_id"):
            source_by_item_id[result["item_id"]] = "mongo_structural_fallback"
    return source_by_item_id


def structured_item_graph_result(item: dict, evidence_source: str) -> dict:
    return {
        "document_id": item.get("document_id"),
        "meeting_id": item.get("meeting_id"),
        "meeting_name": item.get("meeting_name"),
        "meeting_date": item.get("meeting_date"),
        "item_id": item.get("item_id"),
        "item_no": item.get("item_no"),
        "content": item.get("content"),
        "matched_keyword": None,
        "matched_field": "structured_context",
        "matched_relation": "HAS_ITEM",
        "matched_entity": item.get("meeting_name") or item.get("meeting_id"),
        "match_type": "answer_evidence",
        "intent": "structured_context",
        "retrieval_mode": "structured",
        "evidence_source": evidence_source,
        "graph_score": 5.0,
    }


def semantic_item_graph_result(item: dict) -> dict:
    return {
        "document_id": item.get("document_id"),
        "meeting_id": item.get("meeting_id"),
        "meeting_name": item.get("meeting_name"),
        "meeting_date": item.get("meeting_date"),
        "item_id": item.get("item_id"),
        "item_no": item.get("item_no"),
        "content": item.get("content"),
        "matched_keyword": None,
        "matched_field": "semantic_context",
        "matched_relation": "HAS_ITEM",
        "matched_entity": item.get("meeting_name") or item.get("meeting_id"),
        "match_type": "answer_evidence",
        "intent": "semantic_context",
        "retrieval_mode": "semantic",
        "evidence_source": "semantic_context",
        "graph_score": float(item.get("score") or 3.0),
    }


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


def meeting_items_structured_context(
    question: str,
    meetings: list[dict],
    items: list[dict],
    limit: int,
    meeting_hint: str | None = None,
) -> list[dict]:
    matched_meetings = find_meetings_for_structural_question(question, meetings, meeting_hint=meeting_hint)
    if not matched_meetings:
        return []
    matched_meeting_ids = {meeting.get("meeting_id") for meeting in matched_meetings if meeting.get("meeting_id")}
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}
    matched_items = [item for item in items if item.get("meeting_id") in matched_meeting_ids]
    matched_items.sort(key=meeting_item_sort_key)
    context = []
    for item in matched_items:
        meeting = meetings_by_id.get(item.get("meeting_id"), {})
        context.append(format_structured_item(meeting, item))
        if len(context) >= limit:
            break
    return context


def find_meetings_for_structural_question(question: str, meetings: list[dict], meeting_hint: str | None = None) -> list[dict]:
    query = str(question or "").strip()
    hint = str(meeting_hint or "").strip()
    if not query and not hint:
        return []
    normalized_query = normalize_match_text(" ".join(value for value in (query, hint) if value))
    terms = meeting_question_terms(" ".join(value for value in (query, hint) if value))
    scored = []
    for meeting in meetings:
        meeting_id = str(meeting.get("meeting_id") or "")
        meeting_name = str(meeting.get("meeting_name") or "")
        document_id = str(meeting.get("document_id") or "")
        normalized_fields = [
            normalize_match_text(meeting_id),
            normalize_match_text(meeting_name),
            normalize_match_text(document_id),
        ]
        score = 0
        if normalized_fields[0] and normalized_fields[0] in normalized_query:
            score += 100
        if normalized_fields[1] and normalized_fields[1] in normalized_query:
            score += 100
        for term in terms:
            normalized_term = normalize_match_text(term)
            if normalized_term and any(normalized_term in field for field in normalized_fields):
                score += 10 + min(len(normalized_term), 10)
        if score:
            scored.append((score, meeting))
    if not scored:
        return []
    best_score = max(score for score, _meeting in scored)
    threshold = max(best_score * 0.75, best_score - 10)
    return [
        meeting
        for score, meeting in sorted(scored, key=lambda item: (-item[0], str(item[1].get("meeting_date") or "")))
        if score >= threshold
    ]


def meeting_question_terms(question: str) -> list[str]:
    text = str(question or "")
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
        "這場",
        "該場",
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
            terms.append(cleaned)
    return terms[:8]


def normalize_match_text(value) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()


def meeting_item_sort_key(item: dict):
    item_no = str(item.get("item_no") or "")
    match = re.search(r"\d+", item_no)
    numeric = int(match.group(0)) if match else 9999
    return (str(item.get("meeting_id") or ""), numeric, item_no, str(item.get("item_id") or ""))


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
        "status": item.get("status"),
        "status_source": item.get("status_source"),
        "status_confidence": item.get("status_confidence"),
    }


def build_graph_context(
    graph_results: list[dict],
    limit: int = 10,
    query_route: QueryRoute | None = None,
    force_complete: bool = False,
) -> dict:
    paths = []
    seen = set()
    graph_builder = EvidenceGraphBuilder(query_route=query_route)
    evidence_selection = select_graph_evidence_results(
        graph_results,
        limit,
        query_route=query_route,
        force_complete=force_complete,
    )
    for result in evidence_selection["results"]:
        path = format_graph_path(result)
        if path in seen:
            continue
        seen.add(path)
        paths.append(
            {
                "evidence_id": result.get("evidence_id"),
                "meeting_id": result.get("meeting_id"),
                "item_id": result.get("item_id"),
                "matched_keyword": result.get("matched_keyword"),
                "matched_relation": result.get("matched_relation"),
                "matched_entity": result.get("matched_entity"),
                "matched_field": result.get("matched_field"),
                "match_type": result.get("match_type"),
                "intent": result.get("intent"),
                "retrieval_mode": result.get("retrieval_mode"),
                "evidence_source": result.get("evidence_source"),
                "graph_score": result.get("graph_score"),
                "path": path,
            }
        )
        graph_builder.add_result(result)
    summary = {
        key: value
        for key, value in evidence_selection.items()
        if key != "results"
    }
    summary["visible_paths"] = len(paths)
    return {
        "paths": paths,
        "nodes": graph_builder.nodes(),
        "edges": graph_builder.edges(),
        "summary": summary,
    }


def filter_graph_evidence_results(graph_results: list[dict], limit: int) -> list[dict]:
    return select_graph_evidence_results(graph_results, limit)["results"]


def select_graph_evidence_results(
    graph_results: list[dict],
    limit: int,
    query_route: QueryRoute | None = None,
    force_complete: bool = False,
) -> dict:
    candidates = [result for result in graph_results if result.get("meeting_id") or result.get("item_id")]
    if not candidates:
        return evidence_selection([], [], "empty", limit)
    if force_complete:
        return evidence_selection(candidates, candidates, "answer_evidence", limit)
    if should_keep_complete_evidence(candidates, query_route=query_route):
        return evidence_selection(candidates, candidates, "complete_evidence", limit)
    scored = [float(result.get("graph_score") or 0) for result in candidates]
    best_score = max(scored)
    score_floor = max(best_score - 0.75, best_score * 0.82)
    strong_results = [result for result in candidates if float(result.get("graph_score") or 0) >= score_floor]
    if not strong_results:
        strong_results = candidates[:1]
    max_paths = max(1, min(limit, 6))
    selected = strong_results[:max_paths]
    return evidence_selection(candidates, selected, "ranked_preview", limit)


def should_keep_complete_evidence(candidates: list[dict], query_route: QueryRoute | None = None) -> bool:
    if query_route and query_route.query_type in {"structural_list", "relation_lookup", "composite_query", "follow_up_tracking"}:
        return True
    complete_relations = {
        "HAS_ITEM",
        "RESPONSIBLE_BY",
        "ATTENDED_BY",
        "CHAIRED_BY",
        "RECORDED_BY",
        "BELONGS_TO_UNIT",
        "HAS_PLANNED_DATE",
        "HAS_COMPLETED_DATE",
        "TRACKS_ISSUE",
        "FOLLOW_UP_OF",
    }
    relations = {result.get("matched_relation") for result in candidates}
    modes = {result.get("retrieval_mode") for result in candidates}
    return bool(relations) and relations.issubset(complete_relations) and modes.isdisjoint({"keyword", "composite"})


def evidence_selection(candidates: list[dict], selected: list[dict], mode: str, requested_limit: int) -> dict:
    total = len(candidates)
    visible = len(selected)
    return {
        "results": selected,
        "total_paths": total,
        "selected_paths": visible,
        "hidden_paths": max(total - visible, 0),
        "is_truncated": visible < total,
        "selection_mode": mode,
        "requested_limit": requested_limit,
    }


class EvidenceGraphBuilder:
    def __init__(self, query_route: QueryRoute | None = None):
        self._nodes = {}
        self._edges = {}
        self.query_route = query_route

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
                label=meeting_item_label(result),
                title=result.get("content") or item_id,
            )
        if meeting_id and item_id:
            self.add_edge(
                "Meeting",
                meeting_id,
                "MeetingItem",
                item_id,
                "HAS_ITEM",
                evidence_source=result.get("evidence_source") or "neo4j",
            )

        evidence_relations = result.get("evidence_relations") or []
        if evidence_relations:
            for evidence_relation in evidence_relations:
                self.add_evidence_relation(evidence_relation)
            return

        relation = result.get("matched_relation") or "MENTIONS"
        if relation == "HAS_ITEM":
            return

        if relation == "MENTIONS":
            keyword = result.get("matched_keyword") or result.get("matched_entity")
            if keyword and item_id:
                self.add_node("Keyword", keyword, keyword, keyword)
                self.add_edge("MeetingItem", item_id, "Keyword", keyword, "MENTIONS")
            return

        if relation == "FOLLOW_UP_OF":
            if self.should_hide_semantic_node("MeetingItem", relation):
                return
            previous_item_id = result.get("matched_node_id") or result.get("matched_entity")
            if previous_item_id and item_id:
                self.add_node("MeetingItem", previous_item_id, previous_item_id, previous_item_id)
                self.add_edge("MeetingItem", item_id, "MeetingItem", previous_item_id, "FOLLOW_UP_OF")
            return

        entity = result.get("matched_entity")
        if not entity:
            return

        entity_type = entity_type_for_relation(relation)
        if self.should_hide_semantic_node(entity_type, relation):
            return
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
        if self.should_hide_semantic_node(source_type, relation) or self.should_hide_semantic_node(target_type, relation):
            return
        self.add_node(source_type, source_value, evidence_relation.get("source_label") or source_value, source_value)
        self.add_node(target_type, target_value, evidence_relation.get("target_label") or target_value, target_value)
        self.add_edge(
            source_type,
            source_value,
            target_type,
            target_value,
            relation,
            evidence_source=evidence_relation.get("evidence_source") or "neo4j",
        )

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

    def add_edge(self, source_type: str, source_value, target_type: str, target_value, label: str, evidence_source: str = "neo4j") -> None:
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
            "evidence_source": evidence_source,
        }

    def nodes(self) -> list[dict]:
        return list(self._nodes.values())

    def edges(self) -> list[dict]:
        return list(self._edges.values())

    def should_hide_semantic_node(self, node_type: str, relation: str) -> bool:
        semantic_node_types = {"ActionItem", "Decision", "Risk", "Issue"}
        semantic_relations = {"HAS_ACTION", "HAS_DECISION", "HAS_RISK", "TRACKS_ISSUE", "FOLLOW_UP_OF"}
        if node_type not in semantic_node_types and relation not in semantic_relations:
            return False
        if self.query_route and self.query_route.query_type in {"semantic_summary", "follow_up_tracking"}:
            return False
        return True


def make_graph_node_id(node_type: str, value) -> str:
    return f"{node_type}:{str(value or '').strip()}"


def meeting_item_label(result: dict) -> str:
    item_no = str(result.get("item_no") or "").strip()
    item_id = str(result.get("item_id") or "").strip()
    if item_no and item_id:
        return f"{item_no}\n{short_identifier(item_id)}"
    return item_no or short_identifier(item_id) or item_id


def short_identifier(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 10:
        return text
    return text[-8:]


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
        if relation == "HAS_ITEM":
            source = result.get("evidence_source") or "neo4j"
            return f"Meeting({meeting_id})-[:HAS_ITEM {{source: {source}}}]->MeetingItem({item_id})"
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


def build_source_metadata_from_evidence(evidence_records: list[dict]) -> list[dict]:
    sources = []
    seen = set()
    for record in evidence_records:
        payload = record.get("payload") or {}
        key = record.get("evidence_id")
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "evidence_id": record.get("evidence_id"),
                "document_id": payload.get("document_id"),
                "meeting_id": record.get("meeting_id"),
                "item_id": record.get("item_id"),
                "item_no": payload.get("item_no"),
                "meeting_name": payload.get("meeting_name"),
                "evidence_source": record.get("evidence_source"),
                "relation": record.get("relation"),
                "retrieved_by": record.get("retrieved_by"),
                "issue_id": payload.get("issue_id"),
                "issue_title": payload.get("issue_title"),
                "sequence_no": payload.get("sequence_no"),
            }
        )
    return sources


def validate_response_evidence_consistency(payload: dict) -> dict:
    trace = payload.get("trace") or {}
    claim_ids = set((trace.get("answer_claims") or {}).get("evidence_ids") or [])
    graph_ids = {
        path.get("evidence_id")
        for path in ((payload.get("contexts") or {}).get("graph") or {}).get("paths", [])
        if path.get("evidence_id")
    }
    source_ids = {
        source.get("evidence_id")
        for source in payload.get("sources", [])
        if source.get("evidence_id")
    }
    errors = []
    if claim_ids and graph_ids != claim_ids:
        errors.append("graph evidence_ids do not match answer claim evidence_ids")
    if claim_ids and source_ids != claim_ids:
        errors.append("source evidence_ids do not match answer claim evidence_ids")
    if not claim_ids and graph_ids and source_ids and graph_ids != source_ids:
        errors.append("graph evidence_ids do not match source evidence_ids")
    return {
        "is_consistent": not errors,
        "errors": errors,
        "answer_evidence_ids": sorted(claim_ids),
        "graph_evidence_ids": sorted(graph_ids),
        "source_evidence_ids": sorted(source_ids),
    }


def build_graphrag_prompt(
    question: str,
    structured_context: list[dict],
    graph_context: dict,
    semantic_context: list[dict],
    source_metadata: list[dict],
    query_route: QueryRoute | None = None,
    evidence_records: list[dict] | None = None,
) -> str:
    route_payload = query_route.to_dict() if query_route is not None else {}
    evidence_records = evidence_records or []
    return (
        "You are a source-grounded meeting-record GraphRAG claim extractor.\n"
        "Return JSON only. Do not return markdown or prose outside JSON.\n"
        "Use only the selected Canonical Evidence Records.\n"
        'JSON shape: {"answer":"optional concise Traditional Chinese answer",'
        '"claims":[{"claim":"...","evidence_ids":["evidence_001"]}]}\n'
        "Rules:\n"
        "1. Each claim must be directly supported by one or more evidence_ids.\n"
        "2. Do not invent meeting_id, item_id, people, dates, products, or statuses.\n"
        "3. If query_type is structural_list, create one claim per relevant evidence record.\n"
        "4. If query_type is relation_lookup or composite_query, use explicit relation evidence first.\n"
        "5. If query_type is meeting_summary or semantic_summary, or the question asks to summarize/organize, set answer to a concise Traditional Chinese summary and keep claims as its evidence backing.\n"
        "6. If query_type is follow_up_tracking, group claims by issue/timeline and keep chronological sequence from the evidence payload.\n"
        "7. If no evidence supports an answer, return {\"claims\":[]}.\n\n"
        f"Query Route:\n{route_payload}\n\n"
        f"Question:\n{question}\n\n"
        f"Selected Canonical Evidence Records:\n{evidence_records}\n\n"
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


def ollama_evidence_selector(prompt: str) -> str:
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
                        "content": "Select evidence ids only. Return JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "options": {"temperature": 0},
            },
            timeout=int(getattr(settings, "GRAPHRAG_EVIDENCE_SELECTOR_TIMEOUT", 20)),
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise GraphRagServiceError(f"Unable to select GraphRAG evidence: {exc}") from exc

    content = (payload.get("message") or {}).get("content")
    if not content:
        raise GraphRagServiceError("Ollama evidence selector response did not include content.")
    return content


