from __future__ import annotations

import json
import re

from django.conf import settings


SUPPORTED_TARGETS = {"meeting_items", "action_items", "decisions", "risks", "issues"}
SUPPORTED_STATUSES = {"pending", "in_progress", "completed", "not_completed"}
CONSTRAINT_KEYS = {
    "person_name",
    "unit_name",
    "product_name",
    "regulation_name",
    "status",
    "keyword",
}


def analyze_graph_query_plan(question: str, llm_client=None) -> dict:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        return default_plan()

    try:
        content = (llm_client or ollama_graph_query_plan)(normalized_question)
        payload = parse_query_plan_json(content)
    except Exception as exc:
        plan = heuristic_query_plan(normalized_question)
        plan["warnings"] = [f"Graph query planning unavailable: {exc}"]
        return plan

    return normalize_query_plan(payload, normalized_question)


def default_plan() -> dict:
    return {
        "target": "meeting_items",
        "constraints": {key: "" for key in CONSTRAINT_KEYS},
        "include_followups": False,
        "warnings": [],
    }


def ollama_graph_query_plan(question: str) -> str:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    prompt = (
        "Plan graph retrieval for meeting-record GraphRAG.\n"
        "Return JSON only with this shape:\n"
        '{"target":"meeting_items|action_items|decisions|risks|issues",'
        '"constraints":{"person_name":"","unit_name":"","product_name":"","regulation_name":"","status":"","keyword":""},'
        '"include_followups":false}\n'
        "Use status pending, in_progress, completed, or not_completed. "
        "Use risks for risk/issue/problem questions, decisions for decision questions, "
        "action_items for owner/responsibility/progress questions, and issues for cross-meeting tracking. "
        "Put domain terms that are not person/unit/product/regulation into keyword. "
        "Leave unknown constraints empty.\n\n"
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
        timeout=int(getattr(settings, "GRAPH_INTENT_LLM_TIMEOUT", 12)),
    )
    response.raise_for_status()
    payload = response.json()
    content = (payload.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Ollama query-plan response did not include content.")
    return content


def parse_query_plan_json(content: str) -> dict:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Query-plan response was not valid JSON.")
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("Query-plan response JSON must be an object.")
    return payload


def normalize_query_plan(payload: dict, question: str = "") -> dict:
    source = payload if isinstance(payload, dict) else {}
    fallback = heuristic_query_plan(question)
    target = str(source.get("target") or fallback["target"]).strip()
    constraints_source = source.get("constraints") if isinstance(source.get("constraints"), dict) else {}
    constraints = {key: str(constraints_source.get(key) or fallback["constraints"].get(key) or "").strip() for key in CONSTRAINT_KEYS}
    if constraints["status"] not in SUPPORTED_STATUSES:
        constraints["status"] = fallback["constraints"].get("status", "")
    return {
        "target": target if target in SUPPORTED_TARGETS else fallback["target"],
        "constraints": constraints,
        "include_followups": bool(source.get("include_followups") or fallback["include_followups"]),
        "warnings": [],
    }


def heuristic_query_plan(question: str) -> dict:
    plan = default_plan()
    lowered = str(question or "").lower()
    if any(term in lowered for term in ("風險", "問題", "risk", "issue", "concern", "異常")):
        plan["target"] = "risks"
    elif any(term in lowered for term in ("決議", "決定", "decision", "decided", "approved")):
        plan["target"] = "decisions"
    elif any(term in lowered for term in ("追蹤", "進度", "follow", "tracking", "演變", "跨會議")):
        plan["target"] = "issues"
        plan["include_followups"] = True
    elif any(term in lowered for term in ("負責", "owner", "responsible", "待辦", "action")):
        plan["target"] = "action_items"

    if any(term in lowered for term in ("未完成", "尚未", "沒完成", "not completed", "open")):
        plan["constraints"]["status"] = "not_completed"
    elif any(term in lowered for term in ("已完成", "完成", "completed", "closed", "done")):
        plan["constraints"]["status"] = "completed"
    elif any(term in lowered for term in ("進行中", "處理中", "in progress", "ongoing", "pending")):
        plan["constraints"]["status"] = "in_progress"

    regulation = re.search(r"\b(FDA|TFDA|CFDA|PMDA|CE|ISO\s*\d*)\b", question or "", flags=re.I)
    if regulation:
        plan["constraints"]["regulation_name"] = regulation.group(1).strip()
    return plan
