from __future__ import annotations

import json
import re

from django.conf import settings

from apps.graphrag.deterministic import deterministic_query_understanding


SUPPORTED_TARGETS = {"meeting_items", "action_items", "decisions", "risks", "issues"}
SUPPORTED_STATUSES = {"pending", "in_progress", "completed", "not_completed", "not_applicable"}
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

    heuristic_plan = heuristic_query_plan(normalized_question)
    mode = query_planner_mode()
    if mode == "deterministic_only":
        return heuristic_plan
    if not query_planner_llm_available(llm_client):
        return heuristic_plan
    if mode == "deterministic_first" and should_use_deterministic_plan(normalized_question, heuristic_plan):
        return heuristic_plan

    fallback_plan = default_plan() if mode == "llm_only" else heuristic_plan
    try:
        content = (llm_client or ollama_graph_query_plan)(normalized_question)
        payload = parse_query_plan_json(content)
    except Exception as exc:
        fallback_plan["warnings"] = [f"Graph query planning unavailable: {exc}"]
        return fallback_plan

    return normalize_query_plan(payload, normalized_question, fallback_plan=fallback_plan)


def query_planner_mode() -> str:
    raw_mode = str(getattr(settings, "GRAPH_QUERY_PLANNER_MODE", "deterministic_first") or "").strip().lower()
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


def query_planner_llm_available(llm_client=None) -> bool:
    return llm_client is not None or getattr(settings, "GRAPH_QUERY_PLANNER_LLM_ENABLED", True)


def default_plan() -> dict:
    return {
        "target": "meeting_items",
        "constraints": {key: "" for key in CONSTRAINT_KEYS},
        "include_followups": False,
        "warnings": [],
    }


def should_use_deterministic_plan(question: str, plan: dict) -> bool:
    if not re.search(r"[\u4e00-\u9fff]", question):
        return False
    constraints = plan.get("constraints") or {}
    non_empty_constraints = sum(bool(str(value or "").strip()) for value in constraints.values())
    if plan.get("target") in {"risks", "decisions", "issues"}:
        return True
    if constraints.get("status"):
        return True
    return non_empty_constraints >= 2


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


def normalize_query_plan(payload: dict, question: str = "", fallback_plan: dict | None = None) -> dict:
    source = payload if isinstance(payload, dict) else {}
    fallback = fallback_plan or heuristic_query_plan(question)
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
    parsed = deterministic_query_understanding(question)
    entities = parsed["entities"]
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

    if any(term in lowered for term in ("不適用", "不需", "無需", "not applicable", "n/a")):
        plan["constraints"]["status"] = "not_applicable"
    elif any(term in lowered for term in ("未完成", "尚未", "沒完成", "not completed", "open")):
        plan["constraints"]["status"] = "not_completed"
    elif any(term in lowered for term in ("已完成", "實際完成", "完成日期", "completed", "closed", "done")):
        plan["constraints"]["status"] = "completed"
    elif any(term in lowered for term in ("進行中", "處理中", "in progress", "ongoing", "pending")):
        plan["constraints"]["status"] = "in_progress"

    if plan["constraints"]["status"] and plan["target"] == "meeting_items" and any(
        term in lowered for term in ("項目", "事項", "item", "items", "待辦", "action", "完成", "適用")
    ):
        plan["target"] = "action_items"

    for entity_key, constraint_key in (
        ("person_name", "person_name"),
        ("unit_name", "unit_name"),
        ("product_name", "product_name"),
        ("regulation_name", "regulation_name"),
        ("status", "status"),
    ):
        if entities.get(entity_key):
            plan["constraints"][constraint_key] = entities[entity_key]
    if parsed["graph_intent"] == "person_responsibility":
        plan["target"] = "action_items"
    if should_extract_residual_keyword(plan["constraints"]):
        plan["constraints"]["keyword"] = extract_residual_keyword(question)
    return plan


def should_extract_residual_keyword(constraints: dict) -> bool:
    return not any(
        str(constraints.get(key) or "").strip()
        for key in ("person_name", "unit_name", "product_name", "regulation_name", "keyword")
    )


def extract_residual_keyword(question: str) -> str:
    text = str(question or "")
    for cue in (
        "是否已完成",
        "是否完成",
        "已完成",
        "實際完成",
        "完成日期",
        "完成了",
        "未完成",
        "尚未完成",
        "尚未",
        "沒完成",
        "不適用",
        "進行中",
        "處理中",
        "有哪些",
        "哪些",
        "是否",
        "決議",
        "決定",
        "事項",
        "項目",
        "風險",
        "問題",
        "追蹤",
        "摘要",
        "整理",
        "相關",
        "關於",
        "的",
        "嗎",
        "？",
        "?",
    ):
        text = text.replace(cue, " ")
    text = re.sub(r"[\s,，。；;：:（）()\[\]{}<>《》\"'`~!@#$%^&*_+=|\\/.-]+", " ", text)
    tokens = [token.strip() for token in text.split() if len(token.strip()) >= 2]
    return tokens[0] if tokens else ""
