from __future__ import annotations

import json
import os
import re
from pathlib import Path


BASE = Path(__file__).resolve().parent


def load_env() -> None:
    env = BASE / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setup_django() -> None:
    load_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


CASES = [
    {"category": "責任歸屬型", "question": "Person_704118B2B1 負責哪些項目？", "eval": {"type": "owner", "value": "Person_704118B2B1"}},
    {"category": "責任歸屬型", "question": "Person_F03E4ECA0A 負責哪些項目？", "eval": {"type": "owner", "value": "Person_F03E4ECA0A"}},
    {"category": "責任歸屬型", "question": "Person_BDFC2032C6 負責哪些項目？", "eval": {"type": "owner", "value": "Person_BDFC2032C6"}},
    {"category": "時程狀態型", "question": "2017 年 12 月 15 日要完成哪些事項？", "eval": {"type": "planned_date", "value": "2017-12-15"}},
    {"category": "時程狀態型", "question": "2016 年 06 月 05 日要完成哪些事項？", "eval": {"type": "planned_date", "value": "2016-06-05"}},
    {"category": "時程狀態型", "question": "完成日期為 2018-04-13 的事項有哪些？", "eval": {"type": "actual_completed_date", "value": "2018-04-13"}},
    {"category": "關鍵詞探索型", "question": "stem 相關的會議項目有哪些？", "eval": {"type": "keyword", "terms": ["stem"]}},
    {"category": "關鍵詞探索型", "question": "Locking cage 相關的會議項目有哪些？", "eval": {"type": "keyword", "terms": ["locking cage", "locking", "cage"]}},
    {"category": "關鍵詞探索型", "question": "HA coating 相關的會議項目有哪些？", "eval": {"type": "keyword", "terms": ["ha coating", "ha", "coating"]}},
    {"category": "產品或法規關聯型", "question": "CE 相關會議項目有哪些？", "eval": {"type": "token", "value": "CE"}},
    {"category": "產品或法規關聯型", "question": "FDA 相關會議項目有哪些？", "eval": {"type": "token", "value": "FDA"}},
    {"category": "產品或法規關聯型", "question": "TFDA 相關會議項目有哪些？", "eval": {"type": "token", "value": "TFDA"}},
    {"category": "開放模糊型／語意相似型", "question": "P1812 Coformity stem 會議進度與會議摘要", "eval": {"type": "keyword", "terms": ["p1812", "coformity", "stem"]}},
    {"category": "開放模糊型／語意相似型", "question": "Locking cage 設計移轉會議摘要", "eval": {"type": "keyword", "terms": ["locking cage", "locking", "cage", "設計移轉"]}},
    {"category": "開放模糊型／語意相似型", "question": "Fatigue test 相關事項摘要", "eval": {"type": "keyword", "terms": ["fatigue test", "fatigue", "test"]}},
    {"category": "資料不足型", "question": "Person_DEADBEEF00 負責哪些項目？", "eval": {"type": "insufficient"}},
    {"category": "資料不足型", "question": "2099 年 01 月 01 日要完成哪些事項？", "eval": {"type": "insufficient"}},
    {"category": "資料不足型", "question": "Regulation_FAKE000000 相關會議項目有哪些？", "eval": {"type": "insufficient"}},
]


def text_value(value) -> str:
    if value is None:
        return ""
    return str(value)


def evidence_text(source: dict) -> str:
    return "\n".join(
        text_value(source.get(field))
        for field in (
            "meeting_name",
            "meeting_date",
            "item_no",
            "content",
            "owner",
            "planned_date",
            "actual_completed_date",
            "tracking_result",
            "embedding_text",
        )
    )


def compact_evidence(result: dict, index: int) -> dict:
    return {
        "evidence_id": f"evidence_{index:03d}",
        "semantic_score": result.get("semantic_score"),
        "meeting_id": result.get("meeting_id"),
        "item_id": result.get("item_id"),
        "item_no": result.get("item_no"),
        "meeting_name": result.get("meeting_name"),
        "meeting_date": result.get("meeting_date"),
        "content": result.get("content"),
        "owner": result.get("owner"),
        "planned_date": result.get("planned_date"),
        "actual_completed_date": result.get("actual_completed_date"),
        "tracking_result": result.get("tracking_result"),
    }


def call_ollama(prompt: str) -> str:
    from django.conf import settings
    import requests

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/chat"
    response = requests.post(
        url,
        json={
            "model": settings.OLLAMA_INFERENCE_MODEL,
            "stream": False,
            "messages": [
                {"role": "system", "content": "Answer only from supplied evidence. Return JSON only."},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": 0},
        },
        timeout=180,
    )
    response.raise_for_status()
    payload = response.json()
    content = (payload.get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Ollama response did not include content.")
    return content


def build_prompt(question: str, evidence: list[dict]) -> str:
    return (
        "You are a Vector-RAG baseline answerer for enterprise meeting records.\n"
        "Use only the Qdrant vector-retrieved MeetingItem evidence below.\n"
        "Do not use graph relations, database lookup, or outside knowledge.\n"
        "If the evidence does not directly support the question, return an empty claims list.\n"
        "Return JSON only in this shape:\n"
        '{"answer":"concise Traditional Chinese answer or insufficient evidence note",'
        '"claims":[{"claim":"directly supported claim","evidence_ids":["evidence_001"]}]}\n\n'
        f"Question:\n{question}\n\n"
        f"Vector Evidence:\n{json.dumps(evidence, ensure_ascii=False, indent=2)}"
    )


def parse_json_response(raw: str) -> dict:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        payload = json.loads(match.group(0)) if match else {}
    return payload if isinstance(payload, dict) else {}


def normalize_claims(payload: dict, evidence_by_id: dict[str, dict]) -> list[dict]:
    claims = payload.get("claims")
    if not isinstance(claims, list):
        return []
    normalized = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("claim") or "").strip()
        evidence_ids = [
            str(eid).strip()
            for eid in claim.get("evidence_ids", [])
            if str(eid).strip() in evidence_by_id
        ]
        if text and evidence_ids:
            normalized.append({"claim": text, "evidence_ids": evidence_ids})
    return normalized


def source_matches(source: dict, rule: dict) -> bool:
    rule_type = rule.get("type")
    if rule_type == "owner":
        return source.get("owner") == rule.get("value")
    if rule_type == "planned_date":
        return text_value(source.get("planned_date")) == rule.get("value")
    if rule_type == "actual_completed_date":
        return text_value(source.get("actual_completed_date")) == rule.get("value")
    if rule_type == "keyword":
        text = evidence_text(source).lower()
        return any(term.lower() in text for term in rule.get("terms", []))
    if rule_type == "token":
        token = str(rule.get("value") or "")
        text = evidence_text(source)
        return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text, flags=re.I))
    return False


def judge(rule: dict, claims: list[dict], evidence_by_id: dict[str, dict]) -> tuple[str, str]:
    used_sources = [
        evidence_by_id[eid]
        for claim in claims
        for eid in claim.get("evidence_ids", [])
        if eid in evidence_by_id
    ]
    if rule.get("type") == "insufficient":
        if not claims:
            return "正確", "無證據時未產生引用 claims"
        return "錯誤／限制", "資料不足題仍依相似候選產生回答"
    if not claims or not used_sources:
        return "錯誤／限制", "未產生可引用來源的回答"

    matched = [source for source in used_sources if source_matches(source, rule)]
    if len(matched) == len(used_sources):
        return "正確", "引用來源皆符合測試條件"
    if matched:
        return "部分正確", "部分引用來源符合條件，仍混入不符合條件候選"
    return "錯誤／限制", "引用來源未符合測試條件"


def run_case(case: dict) -> dict:
    search_payload = get_cached_or_live_vector_payload(case["question"])
    evidence = [compact_evidence(result, index) for index, result in enumerate(search_payload.get("results", []), start=1)]
    evidence_by_id = {entry["evidence_id"]: entry for entry in evidence}
    prompt = build_prompt(case["question"], evidence)
    llm_error = ""
    if evidence:
        try:
            raw = call_ollama(prompt)
            parsed = parse_json_response(raw)
            claims = normalize_claims(parsed, evidence_by_id)
            mode = "vector_rag_llm"
        except Exception as exc:
            llm_error = f"{type(exc).__name__}: {exc}"
            raw = ""
            parsed = {"answer": "LLM unavailable; evaluated vector evidence candidates only.", "claims": []}
            claims = fallback_claims_from_vector_evidence(evidence)
            mode = "vector_evidence_fallback"
    else:
        raw = '{"answer":"證據不足，無法回答。","claims":[]}'
        parsed = parse_json_response(raw)
        claims = []
        mode = "no_vector_evidence"
    judgement, reason = judge(case["eval"], claims, evidence_by_id)
    return {
        "category": case["category"],
        "question": case["question"],
        "mode": mode,
        "vector_source": search_payload.get("source"),
        "llm_error": llm_error,
        "vector_result_count": len(evidence),
        "top1_item_id": evidence[0].get("item_id") if evidence else None,
        "top1_score": evidence[0].get("semantic_score") if evidence else None,
        "answer": parsed.get("answer") or "",
        "claims": claims,
        "judgement": judgement,
        "judgement_reason": reason,
        "used_item_ids": sorted(
            {
                evidence_by_id[eid].get("item_id")
                for claim in claims
                for eid in claim.get("evidence_ids", [])
                if eid in evidence_by_id and evidence_by_id[eid].get("item_id")
            }
        ),
        "evidence": evidence,
        "raw_llm_response": raw,
    }


def fallback_claims_from_vector_evidence(evidence: list[dict]) -> list[dict]:
    claims = []
    for source in evidence:
        content = str(source.get("content") or "").strip()
        item_no = source.get("item_no")
        prefix = f"item_no {item_no}: " if item_no else ""
        claims.append({"claim": f"{prefix}{content}", "evidence_ids": [source["evidence_id"]]})
    return claims


def get_cached_or_live_vector_payload(question: str) -> dict:
    if os.getenv("VECTOR_RAG_FORCE_LIVE", "").lower() in {"1", "true", "yes", "on"}:
        from apps.vector.services import semantic_search

        payload = semantic_search(question, limit=10)
        payload["source"] = "live_qdrant"
        return payload

    cached = BASE / "vector_baseline_18q_0625.json"
    if cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        for row in data.get("rows", []):
            if row.get("question") == question:
                if row.get("results"):
                    return {
                        "query": question,
                        "score_threshold": row.get("threshold"),
                        "results": row.get("results") or [],
                        "source": "cached_vector_baseline_18q_0625",
                    }
                top_item_ids = [item_id for item_id in row.get("top5_item_ids", []) if item_id]
                if top_item_ids:
                    return {
                        "query": question,
                        "score_threshold": row.get("threshold"),
                        "results": hydrate_cached_vector_results(top_item_ids, row),
                        "source": "cached_vector_baseline_18q_0625_top5",
                    }
    from apps.vector.services import semantic_search

    payload = semantic_search(question, limit=10)
    payload["source"] = "live_qdrant"
    return payload


def hydrate_cached_vector_results(item_ids: list[str], cached_row: dict) -> list[dict]:
    from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection

    items = list(get_meeting_items_collection().find({"item_id": {"$in": item_ids}}, {"_id": 0}))
    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items_by_id = {item.get("item_id"): item for item in items}
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}
    results = []
    for index, item_id in enumerate(item_ids):
        item = items_by_id.get(item_id)
        if not item:
            continue
        meeting = meetings_by_id.get(item.get("meeting_id"), {})
        score = cached_row.get("top1_score") if index == 0 else None
        results.append(
            {
                "document_id": item.get("document_id") or meeting.get("document_id"),
                "meeting_id": item.get("meeting_id"),
                "item_id": item.get("item_id"),
                "item_no": item.get("item_no"),
                "meeting_name": meeting.get("meeting_name"),
                "meeting_date": meeting.get("meeting_date"),
                "content": item.get("content"),
                "owner": item.get("owner"),
                "planned_date": item.get("planned_date"),
                "actual_completed_date": item.get("actual_completed_date"),
                "tracking_result": item.get("tracking_result"),
                "semantic_score": score,
            }
        )
    return results


def main() -> None:
    setup_django()
    rows = []
    for index, case in enumerate(CASES, start=1):
        print(f"[{index}/{len(CASES)}] {case['category']} - {case['question']}", flush=True)
        try:
            rows.append(run_case(case))
        except Exception as exc:
            rows.append(
                {
                    "category": case["category"],
                    "question": case["question"],
                    "mode": "error",
                    "vector_result_count": 0,
                    "judgement": "錯誤／限制",
                    "judgement_reason": f"{type(exc).__name__}: {exc}",
                    "claims": [],
                    "used_item_ids": [],
                    "evidence": [],
                }
            )

    summary = {}
    for category in dict.fromkeys(case["category"] for case in CASES):
        subset = [row for row in rows if row["category"] == category]
        summary[category] = {
            "題數": len(subset),
            "正確": sum(1 for row in subset if row["judgement"] == "正確"),
            "部分正確": sum(1 for row in subset if row["judgement"] == "部分正確"),
            "錯誤／限制": sum(1 for row in subset if row["judgement"] == "錯誤／限制"),
        }
    total = {
        "題數": len(rows),
        "正確": sum(1 for row in rows if row["judgement"] == "正確"),
        "部分正確": sum(1 for row in rows if row["judgement"] == "部分正確"),
        "錯誤／限制": sum(1 for row in rows if row["judgement"] == "錯誤／限制"),
        "資料不足正確拒答": sum(
            1 for row in rows if row["category"] == "資料不足型" and row["judgement"] == "正確"
        ),
    }

    payload = {
        "description": "Vector-RAG baseline: Qdrant top-k MeetingItem evidence + same Ollama inference model; no Neo4j graph query.",
        "settings": {
            "top_k": 10,
            "score_threshold": os.getenv("QDRANT_SCORE_THRESHOLD"),
            "embedding_model": os.getenv("OLLAMA_EMBEDDING_MODEL"),
            "inference_model": os.getenv("OLLAMA_INFERENCE_MODEL"),
        },
        "summary": summary,
        "total": total,
        "rows": rows,
    }
    out = BASE / "vector_rag_18q_0625.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(out)
    print(json.dumps(total, ensure_ascii=False, indent=2))
    for category, data in summary.items():
        print(category, data)


if __name__ == "__main__":
    main()
