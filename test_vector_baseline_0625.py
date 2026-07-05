from __future__ import annotations

import json
import os
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


def main() -> None:
    setup_django()
    from apps.vector.services import semantic_search

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
        try:
            payload = semantic_search(question, limit=10)
            results = payload.get("results", [])
            top = results[0] if results else {}
            rows.append(
                {
                    "category": category,
                    "question": question,
                    "threshold": payload.get("score_threshold"),
                    "result_count": len(results),
                    "top1_score": top.get("semantic_score"),
                    "top1_meeting_id": top.get("meeting_id"),
                    "top1_item_id": top.get("item_id"),
                    "top1_item_no": top.get("item_no"),
                    "top1_content": top.get("content"),
                    "top5_item_ids": [item.get("item_id") for item in results[:5]],
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "category": category,
                    "question": question,
                    "error": f"{type(exc).__name__}: {exc}",
                    "result_count": 0,
                }
            )

    summary = {}
    for category in dict.fromkeys(category for category, _ in cases):
        subset = [row for row in rows if row["category"] == category]
        summary[category] = {
            "questions": len(subset),
            "has_vector_results": sum(1 for row in subset if row.get("result_count", 0) > 0),
            "empty_results": sum(1 for row in subset if row.get("result_count", 0) == 0),
        }

    out = BASE / "vector_baseline_18q_0625.json"
    out.write_text(
        json.dumps({"description": "Vector baseline test for balanced 18 GraphRAG questions.", "summary": summary, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(out)
    print("summary")
    for category, data in summary.items():
        print(category, data)
    print("rows")
    for i, row in enumerate(rows, 1):
        print(
            f"{i}. {row['category']} | count={row.get('result_count')} | "
            f"top1={row.get('top1_score')} | {row['question']} | {row.get('top1_item_id')}"
        )


if __name__ == "__main__":
    main()
