from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .services import answer_question, validate_response_evidence_consistency


DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "fixtures" / "graphrag_golden_cases.json"


def load_golden_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        return payload["cases"]
    raise ValueError("Golden cases file must be a JSON list or an object with a 'cases' list.")


def write_golden_cases(cases: list[dict], path: str | Path, *, description: str | None = None) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"cases": cases}
    if description:
        payload = {"description": description, "cases": cases}
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def save_approved_golden_cases(
    cases: list[dict],
    path: str | Path = DEFAULT_CASES_PATH,
) -> dict:
    approved_cases = [sanitize_golden_case(case) for case in cases if is_approved_case(case)]
    approved_cases = [case for case in approved_cases if case_has_expectations(case)]
    if not approved_cases:
        return {"saved": 0, "skipped": len(cases), "path": str(path), "cases": load_cases_if_exists(path)}

    existing_cases = load_cases_if_exists(path)
    by_id = {str(case.get("id")): case for case in existing_cases if case.get("id")}
    created = 0
    updated = 0
    for case in approved_cases:
        if case["id"] in by_id:
            updated += 1
        else:
            created += 1
        by_id[case["id"]] = case

    merged_cases = list(by_id.values())
    write_golden_cases(
        merged_cases,
        path,
        description="GraphRAG golden cases. Approved cases are used by eval_graphrag.",
    )
    return {
        "saved": len(approved_cases),
        "created": created,
        "updated": updated,
        "skipped": len(cases) - len(approved_cases),
        "path": str(path),
        "cases": merged_cases,
    }


def load_cases_if_exists(path: str | Path) -> list[dict]:
    source = Path(path)
    if not source.exists():
        return []
    return load_golden_cases(source)


def is_approved_case(case: dict) -> bool:
    return bool(case.get("enabled")) or str(case.get("review_status") or "").strip().lower() == "approved"


def case_has_expectations(case: dict) -> bool:
    return bool(
        case.get("expect_insufficient")
        or normalize_list(case.get("expected_item_ids"))
        or normalize_list(case.get("expected_meeting_ids"))
        or normalize_list(case.get("expected_relations"))
        or normalize_list(case.get("expected_answer_contains"))
    )


def sanitize_golden_case(case: dict) -> dict:
    question = str(case.get("question") or "").strip()
    case_id = str(case.get("id") or make_case_id(question, 1)).strip()
    sanitized = {
        "id": case_id,
        "enabled": True,
        "question": question,
        "limit": str(case.get("limit") or "auto").strip() or "auto",
        "expected_item_ids": normalize_list(case.get("expected_item_ids")),
        "expected_meeting_ids": normalize_list(case.get("expected_meeting_ids")),
        "expected_relations": normalize_list(case.get("expected_relations")),
        "unexpected_item_ids": normalize_list(case.get("unexpected_item_ids")),
        "require_consistency": bool(case.get("require_consistency", True)),
        "review_status": "approved",
    }
    if case.get("expect_insufficient"):
        sanitized["expect_insufficient"] = True
    for key in ("expected_answer_contains", "expected_answer_not_contains"):
        values = normalize_list(case.get(key))
        if values:
            sanitized[key] = values
    return sanitized


def load_questions(path: str | Path) -> list[str]:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            return [str(item.get("question") if isinstance(item, dict) else item).strip() for item in payload if item]
        if isinstance(payload, dict) and isinstance(payload.get("questions"), list):
            return [str(item).strip() for item in payload["questions"] if str(item).strip()]
        if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
            return [str(item.get("question") or "").strip() for item in payload["cases"] if item.get("question")]
        raise ValueError("Question JSON must be a list, {'questions': [...]}, or {'cases': [...]}.")
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def seed_golden_cases_from_questions(
    questions: list[str],
    *,
    answerer: Callable[..., dict] = answer_question,
    enabled: bool = False,
    limit: str = "auto",
) -> list[dict]:
    cases = []
    for index, question in enumerate(questions, start=1):
        payload = answerer(question, limit=limit)
        cases.append(seed_case_from_payload(question, payload, index=index, enabled=enabled, limit=limit))
    return cases


def seed_case_from_payload(question: str, payload: dict, *, index: int, enabled: bool = False, limit: str = "auto") -> dict:
    contexts = payload.get("contexts") or {}
    graph = contexts.get("graph") or {}
    paths = graph.get("paths") or []
    sources = payload.get("sources") or []
    trace = payload.get("trace") or {}
    consistency = validate_response_evidence_consistency(payload)
    item_ids = sorted({str(source.get("item_id")) for source in sources if source.get("item_id")})
    meeting_ids = sorted({str(source.get("meeting_id")) for source in sources if source.get("meeting_id")})
    relations = sorted({str(path.get("matched_relation")) for path in paths if path.get("matched_relation")})
    case = {
        "id": make_case_id(question, index),
        "enabled": enabled,
        "question": question,
        "limit": limit,
        "expected_item_ids": item_ids,
        "expected_meeting_ids": meeting_ids,
        "expected_relations": relations,
        "unexpected_item_ids": [],
        "require_consistency": True,
        "review_status": "needs_review",
        "observed": {
            "answer": payload.get("answer"),
            "route": trace.get("route", {}),
            "evidence_consistency": consistency,
        },
    }
    if trace.get("is_insufficient"):
        case["expect_insufficient"] = True
    return case


def make_case_id(question: str, index: int) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in question).strip("_")
    slug = "_".join(part for part in slug.split("_") if part)
    if not slug:
        slug = "question"
    return f"seed_{index:03d}_{slug[:48]}"


def evaluate_golden_cases(
    cases: list[dict],
    *,
    answerer: Callable[..., dict] = answer_question,
) -> dict:
    results = []
    for index, case in enumerate(cases, start=1):
        case_id = str(case.get("id") or f"case_{index:03d}")
        if case.get("enabled") is False:
            results.append({"id": case_id, "status": "skipped", "failures": [], "case": case})
            continue
        try:
            payload = answerer(case["question"], limit=case.get("limit", "auto"))
            result = evaluate_payload(case, payload)
        except Exception as exc:
            result = {
                "id": case_id,
                "status": "failed",
                "failures": [f"raised exception: {exc}"],
                "case": case,
                "payload": None,
            }
        results.append(result)

    enabled = [result for result in results if result["status"] != "skipped"]
    passed = [result for result in enabled if result["status"] == "passed"]
    failed = [result for result in enabled if result["status"] == "failed"]
    skipped = [result for result in results if result["status"] == "skipped"]
    return {
        "summary": {
            "total": len(results),
            "enabled": len(enabled),
            "passed": len(passed),
            "failed": len(failed),
            "skipped": len(skipped),
        },
        "results": results,
    }


def evaluate_payload(case: dict, payload: dict) -> dict:
    failures = []
    answer = str(payload.get("answer") or "")
    contexts = payload.get("contexts") or {}
    graph = contexts.get("graph") or {}
    graph_paths = graph.get("paths") or []
    sources = payload.get("sources") or []
    trace = payload.get("trace") or {}

    if case.get("expect_insufficient") is True:
        if not trace.get("is_insufficient") and "Insufficient meeting-record context" not in answer:
            failures.append("expected insufficient-context response")
    elif "Insufficient meeting-record context" in answer:
        failures.append("unexpected insufficient-context response")

    expected_item_ids = normalize_list(case.get("expected_item_ids"))
    unexpected_item_ids = normalize_list(case.get("unexpected_item_ids"))
    expected_meeting_ids = normalize_list(case.get("expected_meeting_ids"))
    expected_relations = normalize_list(case.get("expected_relations"))

    answer_text = answer.lower()
    source_item_ids = {str(source.get("item_id")) for source in sources if source.get("item_id")}
    graph_item_ids = {str(path.get("item_id")) for path in graph_paths if path.get("item_id")}
    source_meeting_ids = {str(source.get("meeting_id")) for source in sources if source.get("meeting_id")}
    graph_meeting_ids = {str(path.get("meeting_id")) for path in graph_paths if path.get("meeting_id")}
    graph_relations = {str(path.get("matched_relation")) for path in graph_paths if path.get("matched_relation")}

    for item_id in expected_item_ids:
        if item_id.lower() not in answer_text:
            failures.append(f"answer missing expected item_id: {item_id}")
        if item_id not in source_item_ids:
            failures.append(f"sources missing expected item_id: {item_id}")
        if item_id not in graph_item_ids:
            failures.append(f"graph missing expected item_id: {item_id}")

    for item_id in unexpected_item_ids:
        if item_id.lower() in answer_text or item_id in source_item_ids or item_id in graph_item_ids:
            failures.append(f"unexpected item_id present: {item_id}")

    for meeting_id in expected_meeting_ids:
        if meeting_id.lower() not in answer_text:
            failures.append(f"answer missing expected meeting_id: {meeting_id}")
        if meeting_id not in source_meeting_ids and meeting_id not in graph_meeting_ids:
            failures.append(f"evidence missing expected meeting_id: {meeting_id}")

    for relation in expected_relations:
        if relation not in graph_relations:
            failures.append(f"graph missing expected relation: {relation}")

    for text in normalize_list(case.get("expected_answer_contains")):
        if text.lower() not in answer_text:
            failures.append(f"answer missing expected text: {text}")

    for text in normalize_list(case.get("expected_answer_not_contains")):
        if text.lower() in answer_text:
            failures.append(f"answer contains forbidden text: {text}")

    if case.get("require_consistency", True):
        consistency = validate_response_evidence_consistency(payload)
        if not consistency["is_consistent"]:
            failures.extend(consistency["errors"])
    else:
        consistency = validate_response_evidence_consistency(payload)

    return {
        "id": str(case.get("id") or "case"),
        "status": "failed" if failures else "passed",
        "failures": failures,
        "case": case,
        "consistency": consistency,
        "observed": {
            "answer": answer,
            "source_item_ids": sorted(source_item_ids),
            "graph_item_ids": sorted(graph_item_ids),
            "graph_relations": sorted(graph_relations),
            "route": trace.get("route", {}),
        },
    }


def normalize_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if str(item)]
