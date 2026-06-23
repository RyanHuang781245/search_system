from __future__ import annotations

from dataclasses import asdict, dataclass
from dataclasses import field
import json
import re

from django.conf import settings

from apps.graphrag.deterministic import (
    contains_date,
    contains_regulation,
    deterministic_query_understanding,
    is_probable_person_name,
)


@dataclass(frozen=True)
class QueryRoute:
    query_type: str
    retrieval_modes: tuple[str, ...]
    use_semantic: bool
    allow_keyword_fallback: bool
    default_limit: int
    limit_mode: str
    answer_style: str
    confidence: float | str = "heuristic"
    route_source: str = "heuristic"
    entities: dict = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["retrieval_modes"] = list(self.retrieval_modes)
        payload["warnings"] = list(self.warnings)
        return payload


def analyze_query_route(question: str, llm_client=None) -> QueryRoute:
    heuristic_route = route_question(question)
    mode = query_router_mode()
    if mode == "deterministic_only":
        return replace_route_metadata(heuristic_route, route_source="heuristic")
    if not query_router_llm_available(llm_client):
        return replace_route_metadata(heuristic_route, route_source="heuristic")
    if mode == "deterministic_first" and llm_client is None and should_use_deterministic_route(heuristic_route):
        return replace_route_metadata(heuristic_route, route_source="heuristic")

    fallback_route = empty_open_route() if mode == "llm_only" else heuristic_route
    try:
        content = (llm_client or ollama_query_understanding)(question)
        payload = parse_query_understanding_json(content)
        return normalize_llm_route(payload, fallback_route)
    except Exception as exc:
        return replace_route_metadata(
            fallback_route,
            route_source="llm_fallback" if mode == "llm_only" else "heuristic_fallback",
            warnings=(f"LLM query understanding unavailable: {exc}",),
        )


def query_router_mode() -> str:
    raw_mode = str(getattr(settings, "GRAPHRAG_QUERY_ROUTER_MODE", "deterministic_first") or "").strip().lower()
    aliases = {
        "heuristic_first": "deterministic_first",
        "rules_first": "deterministic_first",
        "llm": "llm_first",
        "heuristic_only": "deterministic_only",
        "rules_only": "deterministic_only",
    }
    mode = aliases.get(raw_mode, raw_mode)
    if mode not in {"deterministic_first", "llm_first", "deterministic_only", "llm_only"}:
        return "deterministic_first"
    return mode


def query_router_llm_available(llm_client=None) -> bool:
    return llm_client is not None or getattr(settings, "GRAPHRAG_QUERY_ROUTER_LLM_ENABLED", True)


def empty_open_route() -> QueryRoute:
    return replace_route_metadata(make_route("open_qa"), route_source="llm_only", entities=normalize_entities({}))


def should_use_deterministic_route(route: QueryRoute) -> bool:
    if route.query_type != "open_qa":
        return True
    return any(str(route.entities.get(key) or "").strip() for key in (
        "meeting_hint",
        "person_name",
        "date_value",
        "product_name",
        "regulation_name",
        "status",
    ))


def route_question(question: str) -> QueryRoute:
    text = str(question or "").strip()
    parsed = deterministic_query_understanding(text)
    route = make_route(parsed["query_type"])
    return replace_route_metadata(route, entities=parsed["entities"])


def ollama_query_understanding(question: str) -> str:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    prompt = (
        "Analyze a meeting-record GraphRAG question.\n"
        "Return JSON only with this exact shape:\n"
        '{"query_type":"structural_list|relation_lookup|composite_query|meeting_summary|semantic_summary|follow_up_tracking|keyword_exploration|open_qa",'
        '"entities":{"meeting_hint":"","person_name":"","date_value":"","product_name":"","regulation_name":"","status":"","keyword":""},'
        '"confidence":0.0}\n'
        "Rules:\n"
        "- structural_list: user asks for all items, discussion items, agenda, topics, or contents of a specific meeting.\n"
        "- relation_lookup: user asks what a person/unit/date is responsible for or related to.\n"
        "- composite_query: user combines person/product/regulation/status constraints.\n"
        "- meeting_summary: user asks to summarize, organize, or extract highlights from one specific meeting.\n"
        "- semantic_summary: risks, decisions, issues, follow-up summaries.\n"
        "- follow_up_tracking: cross-meeting issue/follow-up tracking, later handling, or issue timeline questions.\n"
        "- keyword_exploration: mentions/about/related to a keyword, regulation, product, or term.\n"
        "- open_qa: broad summarization or unclear questions.\n"
        "Extract meeting_hint from partial or full meeting names such as P1812, HA-Fit, Conformity stem.\n"
        "Do not generate Cypher or database queries.\n\n"
        f"Question:\n{question}"
    )
    response = requests.post(
        url,
        json={
            "model": settings.OLLAMA_INFERENCE_MODEL,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0},
        },
        timeout=int(getattr(settings, "GRAPHRAG_QUERY_ROUTER_LLM_TIMEOUT", 8)),
    )
    response.raise_for_status()
    payload = response.json()
    content = (payload.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Ollama query understanding response did not include content.")
    return content


def parse_query_understanding_json(content: str) -> dict:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Query understanding response was not valid JSON.")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Query understanding JSON must be an object.")
    return payload


def normalize_llm_route(payload: dict, fallback_route: QueryRoute) -> QueryRoute:
    query_type = str(payload.get("query_type") or "").strip()
    if query_type not in route_specs():
        query_type = fallback_route.query_type
    route = make_route(query_type)
    confidence = payload.get("confidence")
    entities = normalize_entities(payload.get("entities") if isinstance(payload.get("entities"), dict) else {})
    return replace_route_metadata(
        route,
        route_source="llm",
        confidence=normalize_confidence(confidence),
        entities=merge_entities(fallback_route.entities, entities),
    )


def make_route(query_type: str) -> QueryRoute:
    spec = route_specs().get(query_type) or route_specs()["open_qa"]
    return QueryRoute(query_type=query_type if query_type in route_specs() else "open_qa", **spec)


def route_specs() -> dict:
    return {
        "structural_list": {
            "retrieval_modes": ("structural",),
            "use_semantic": False,
            "allow_keyword_fallback": False,
            "default_limit": 50,
            "limit_mode": "auto:structural_list",
            "answer_style": "complete_list",
        },
        "relation_lookup": {
            "retrieval_modes": ("relation",),
            "use_semantic": False,
            "allow_keyword_fallback": True,
            "default_limit": 20,
            "limit_mode": "auto:relation",
            "answer_style": "relation_facts",
        },
        "composite_query": {
            "retrieval_modes": ("composite", "relation"),
            "use_semantic": False,
            "allow_keyword_fallback": True,
            "default_limit": 15,
            "limit_mode": "auto:composite",
            "answer_style": "filtered_evidence",
        },
        "meeting_summary": {
            "retrieval_modes": ("structural",),
            "use_semantic": True,
            "allow_keyword_fallback": False,
            "default_limit": 50,
            "limit_mode": "auto:meeting_summary",
            "answer_style": "meeting_summary",
        },
        "semantic_summary": {
            "retrieval_modes": ("composite",),
            "use_semantic": True,
            "allow_keyword_fallback": True,
            "default_limit": 12,
            "limit_mode": "auto:semantic_summary",
            "answer_style": "summary",
        },
        "follow_up_tracking": {
            "retrieval_modes": ("follow_up",),
            "use_semantic": False,
            "allow_keyword_fallback": False,
            "default_limit": 30,
            "limit_mode": "auto:follow_up_tracking",
            "answer_style": "timeline",
        },
        "keyword_exploration": {
            "retrieval_modes": ("keyword",),
            "use_semantic": True,
            "allow_keyword_fallback": True,
            "default_limit": 10,
            "limit_mode": "auto:keyword",
            "answer_style": "evidence_summary",
        },
        "open_qa": {
            "retrieval_modes": ("structural", "composite", "relation", "keyword"),
            "use_semantic": True,
            "allow_keyword_fallback": True,
            "default_limit": 8,
            "limit_mode": "auto:open_qa",
            "answer_style": "grounded_answer",
        },
    }


def replace_route_metadata(
    route: QueryRoute,
    *,
    route_source: str | None = None,
    confidence=None,
    entities: dict | None = None,
    warnings: tuple[str, ...] | list[str] | None = None,
) -> QueryRoute:
    return QueryRoute(
        query_type=route.query_type,
        retrieval_modes=route.retrieval_modes,
        use_semantic=route.use_semantic,
        allow_keyword_fallback=route.allow_keyword_fallback,
        default_limit=route.default_limit,
        limit_mode=route.limit_mode,
        answer_style=route.answer_style,
        confidence=route.confidence if confidence is None else confidence,
        route_source=route.route_source if route_source is None else route_source,
        entities=route.entities if entities is None else entities,
        warnings=route.warnings if warnings is None else tuple(warnings),
    )


def normalize_entities(entities: dict) -> dict:
    keys = ("meeting_hint", "person_name", "date_value", "product_name", "regulation_name", "status", "keyword")
    return {key: str(entities.get(key) or "").strip() for key in keys}


def merge_entities(base: dict, override: dict) -> dict:
    entities = normalize_entities(base or {})
    entities.update({key: value for key, value in normalize_entities(override or {}).items() if value})
    return entities


def normalize_confidence(value):
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return "llm"


def is_structural_item_list_question(text: str) -> bool:
    return has_any(text, ("\u6703\u8b70", "meeting")) and has_any(
        text,
        (
            "\u9805\u76ee",
            "\u4e8b\u9805",
            "\u8a0e\u8ad6\u4e8b\u9805",
            "\u8b70\u984c",
            "item",
            "agenda",
            "topic",
            "\u5167\u5bb9",
            "\u5305\u542b",
            "\u6709\u54ea\u4e9b",
            "\u54ea\u4e9b",
            "\u5217\u51fa",
        ),
    )


def is_composite_question(original: str, lowered: str) -> bool:
    signal_count = 0
    if has_any(lowered, ("\u8ca0\u8cac", "owner", "responsible", "\u8ab0\u8ca0\u8cac")) or is_probable_person_name(original):
        signal_count += 1
    if contains_regulation(original):
        signal_count += 1
    if has_any(lowered, ("\u7522\u54c1", "product", "stem", "cage", "handle", "conformity", "p1812")):
        signal_count += 1
    if has_any(lowered, ("\u672a\u5b8c\u6210", "\u5c1a\u672a\u5b8c\u6210", "\u9032\u884c\u4e2d", "open", "pending", "not completed")):
        signal_count += 1
    return signal_count >= 2 and has_any(
        lowered,
        ("\u9805\u76ee", "item", "items", "\u98a8\u96aa", "risk", "\u6c7a\u8b70", "decision", "\u8ffd\u8e64", "follow"),
    )


def is_relation_lookup_question(original: str, lowered: str) -> bool:
    if contains_date(original):
        return True
    if has_any(
        lowered,
        (
            "\u8ca0\u8cac",
            "\u8ab0\u8ca0\u8cac",
            "\u51fa\u5e2d",
            "\u4e3b\u6301",
            "\u8a18\u9304",
            "\u55ae\u4f4d",
            "owner",
            "responsible",
            "attended",
            "chair",
            "recorder",
            "unit",
        ),
    ):
        return True
    return is_probable_person_name(original)


def contains_date(text: str) -> bool:
    return bool(
        re.search(r"\d{4}\s*[-/]\s*\d{1,2}(?:\s*[-/]\s*\d{1,2})?", str(text or ""))
        or re.search(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?", str(text or ""))
    )


def is_semantic_summary_question(text: str) -> bool:
    return has_any(
        text,
        (
            "\u98a8\u96aa",
            "\u6c7a\u8b70",
            "\u6c7a\u5b9a",
            "\u8ffd\u8e64",
            "\u554f\u984c",
            "risk",
            "decision",
            "follow-up",
            "follow up",
            "issue",
        ),
    )


def is_keyword_exploration_question(original: str, lowered: str) -> bool:
    return contains_regulation(original) or has_any(
        lowered,
        ("\u76f8\u95dc", "\u63d0\u5230", "\u95dc\u65bc", "related", "mentions", "about", "fda", "tfda", "cfda", "pmda"),
    )


def is_probable_person_name(text: str) -> bool:
    value = str(text or "").strip()
    if not value or contains_regulation(value):
        return False
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value):
        return True
    if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?", value):
        return True
    return False


def contains_regulation(text: str) -> bool:
    return bool(re.search(r"\b(FDA|TFDA|CFDA|PMDA|CE|ISO\s*\d*)\b", str(text or ""), flags=re.I))


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
