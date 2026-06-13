from __future__ import annotations

import json
import re

from django.conf import settings


SUPPORTED_GRAPH_INTENTS = {
    "person_responsibility",
    "person_attendance",
    "meeting_chair",
    "meeting_recorder",
    "unit_meetings",
    "planned_date",
    "completed_date",
    "product_related",
    "regulation_related",
    "keyword_related",
}


def analyze_graph_intent(question: str, llm_client=None) -> dict:
    normalized_question = str(question or "").strip()
    if not normalized_question:
        return {"intent": "keyword_related", "entities": {}, "warnings": []}

    try:
        content = (llm_client or ollama_graph_intent)(normalized_question)
        payload = parse_intent_json(content)
    except Exception as exc:
        return {
            "intent": "keyword_related",
            "entities": {},
            "warnings": [f"Graph intent analysis unavailable: {exc}"],
        }

    intent = normalize_intent(payload.get("intent"))
    entities = normalize_entities(payload.get("entities"))
    warnings = []
    if intent == "keyword_related" and payload.get("intent") not in {None, "keyword_related"}:
        warnings.append(f"Unsupported graph intent '{payload.get('intent')}', using keyword_related.")

    return {
        "intent": intent,
        "entities": entities,
        "warnings": warnings,
    }


def ollama_graph_intent(question: str) -> str:
    try:
        import requests
    except Exception as exc:
        raise RuntimeError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    prompt = (
        "Classify this meeting-record question for graph retrieval.\n"
        "Return JSON only with this shape:\n"
        '{"intent":"person_responsibility|person_attendance|meeting_chair|meeting_recorder|'
        'unit_meetings|planned_date|completed_date|product_related|regulation_related|keyword_related",'
        '"entities":{"person_name":"","unit_name":"","date_value":"","product_name":"","regulation_name":"","keyword":""}}\n'
        "Use person_responsibility for owner/responsible item questions. "
        "Use keyword_related when no relation-specific intent fits. "
        "Leave an entity empty when the question asks for all records.\n\n"
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
        raise RuntimeError("Ollama intent response did not include content.")
    return content


def parse_intent_json(content: str) -> dict:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Intent response was not valid JSON.")
        payload = json.loads(match.group(0))

    if not isinstance(payload, dict):
        raise ValueError("Intent response JSON must be an object.")
    return payload


def normalize_intent(value) -> str:
    intent = str(value or "keyword_related").strip()
    return intent if intent in SUPPORTED_GRAPH_INTENTS else "keyword_related"


def normalize_entities(value) -> dict:
    source = value if isinstance(value, dict) else {}
    allowed = {
        "person_name",
        "unit_name",
        "date_value",
        "product_name",
        "regulation_name",
        "keyword",
    }
    return {key: str(source.get(key) or "").strip() for key in allowed}
