from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
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


def run_question(question: str):
    from apps.graphrag.services import answer_question, validate_response_evidence_consistency

    payload = answer_question(
        question,
        limit="auto",
        # Keep this run focused on retrieval/evidence rather than prose generation.
        llm_client=lambda _prompt: '{"claims":[]}',
    )
    trace = payload.get("trace") or {}
    contexts = payload.get("contexts") or {}
    graph = contexts.get("graph") or {}
    paths = graph.get("paths") or []
    sources = payload.get("sources") or []
    return {
        "question": question,
        "answer": payload.get("answer"),
        "route": trace.get("route") or payload.get("query_route") or {},
        "source_count": len(sources),
        "graph_path_count": len(paths),
        "is_insufficient": bool(trace.get("is_insufficient")),
        "relations": sorted({str(path.get("matched_relation")) for path in paths if path.get("matched_relation")}),
        "source_item_ids": sorted({str(source.get("item_id")) for source in sources if source.get("item_id")}),
        "source_meeting_ids": sorted({str(source.get("meeting_id")) for source in sources if source.get("meeting_id")}),
        "consistency": validate_response_evidence_consistency(payload),
        "warnings": payload.get("warnings") or trace.get("warnings") or [],
    }


def judge(category: str, result: dict) -> str:
    if category == "資料不足型":
        return "正確" if result["is_insufficient"] and result["consistency"]["is_consistent"] else "錯誤"
    if not result["source_count"] or result["is_insufficient"]:
        return "錯誤"
    if not result["consistency"]["is_consistent"]:
        return "錯誤"
    if category == "關鍵詞探索型":
        return "部分正確"
    if category == "產品或法規關聯型" and result["question"].startswith("TFDA"):
        return "部分正確"
    return "正確"


def main() -> None:
    setup_django()

    cases = [
        ("責任歸屬型", "Person_704118B2B1 負責哪些項目？"),
        ("責任歸屬型", "Person_F03E4ECA0A 負責哪些項目？"),
        ("責任歸屬型", "Person_BDFC2032C6 負責哪些項目？"),
        ("時程狀態型", "2017 年 12 月 15 日要完成哪些事項？"),
        ("時程狀態型", "2016 年 06 月 05 日要完成哪些事項？"),
        ("時程狀態型", "完成日期為 2018-04-13 的事項有哪些？"),
        ("關鍵詞探索型", "stem 相關的會議項目有哪些？"),
        ("關鍵詞探索型", "Locking cage 相關的會議項目有哪些？"),
        ("關鍵詞探索型", "HA coating 相關的會議項目有哪些？"),
        ("產品或法規關聯型", "CE 相關會議項目有哪些？"),
        ("產品或法規關聯型", "FDA 相關會議項目有哪些？"),
        ("產品或法規關聯型", "TFDA 相關會議項目有哪些？"),
        ("開放模糊型／語意相似型", "P1812 Coformity stem 會議進度與會議摘要"),
        ("開放模糊型／語意相似型", "Locking cage 設計移轉會議摘要"),
        ("開放模糊型／語意相似型", "Fatigue test 相關事項摘要"),
        ("資料不足型", "Person_DEADBEEF00 負責哪些項目？"),
        ("資料不足型", "2099 年 01 月 01 日要完成哪些事項？"),
        ("資料不足型", "Regulation_FAKE000000 相關會議項目有哪些？"),
    ]

    rows = []
    for category, question in cases:
        result = run_question(question)
        result["category"] = category
        result["judgement"] = judge(category, result)
        rows.append(result)

    summary = defaultdict(Counter)
    for row in rows:
        summary[row["category"]]["題數"] += 1
        summary[row["category"]][row["judgement"]] += 1

    payload = {
        "description": "Balanced GraphRAG retest, 6 categories x 3 questions, deidentified data.",
        "rows": rows,
        "summary": {category: dict(counter) for category, counter in summary.items()},
    }
    out = BASE / "graphrag_balanced_retest_0625.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(out)
    for category, counter in summary.items():
        print(category, dict(counter))
    print("total", len(rows), Counter(row["judgement"] for row in rows))


if __name__ == "__main__":
    main()
