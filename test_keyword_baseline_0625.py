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
    {
        "category": "責任歸屬型",
        "question": "Person_704118B2B1 負責哪些項目？",
        "terms": ["Person_704118B2B1"],
    },
    {
        "category": "責任歸屬型",
        "question": "Person_F03E4ECA0A 負責哪些項目？",
        "terms": ["Person_F03E4ECA0A"],
    },
    {
        "category": "責任歸屬型",
        "question": "Person_BDFC2032C6 負責哪些項目？",
        "terms": ["Person_BDFC2032C6"],
    },
    {
        "category": "時程狀態型",
        "question": "2017 年 12 月 15 日要完成哪些事項？",
        "terms": ["2017-12-15", "2017/12/15", "2017 年 12 月 15 日"],
    },
    {
        "category": "時程狀態型",
        "question": "2016 年 06 月 05 日要完成哪些事項？",
        "terms": ["2016-06-05", "2016/06/05", "2016 年 06 月 05 日"],
    },
    {
        "category": "時程狀態型",
        "question": "完成日期為 2018-04-13 的事項有哪些？",
        "terms": ["2018-04-13", "2018/04/13"],
    },
    {
        "category": "關鍵詞探索型",
        "question": "stem 相關的會議項目有哪些？",
        "terms": ["stem"],
    },
    {
        "category": "關鍵詞探索型",
        "question": "Locking cage 相關的會議項目有哪些？",
        "terms": ["Locking cage", "Locking", "cage"],
    },
    {
        "category": "關鍵詞探索型",
        "question": "HA coating 相關的會議項目有哪些？",
        "terms": ["HA coating", "HA", "coating"],
    },
    {
        "category": "產品或法規關聯型",
        "question": "CE 相關會議項目有哪些？",
        "terms": ["CE"],
    },
    {
        "category": "產品或法規關聯型",
        "question": "FDA 相關會議項目有哪些？",
        "terms": ["FDA"],
    },
    {
        "category": "產品或法規關聯型",
        "question": "TFDA 相關會議項目有哪些？",
        "terms": ["TFDA"],
    },
    {
        "category": "開放模糊型／語意相似型",
        "question": "P1812 Coformity stem 會議進度與會議摘要",
        "terms": ["P1812", "Coformity", "stem"],
    },
    {
        "category": "開放模糊型／語意相似型",
        "question": "Locking cage 設計移轉會議摘要",
        "terms": ["Locking cage", "Locking", "cage", "設計移轉"],
    },
    {
        "category": "開放模糊型／語意相似型",
        "question": "Fatigue test 相關事項摘要",
        "terms": ["Fatigue test", "Fatigue", "test"],
    },
    {
        "category": "資料不足型",
        "question": "Person_DEADBEEF00 負責哪些項目？",
        "terms": ["Person_DEADBEEF00"],
    },
    {
        "category": "資料不足型",
        "question": "2099 年 01 月 01 日要完成哪些事項？",
        "terms": ["2099-01-01", "2099/01/01", "2099 年 01 月 01 日"],
    },
    {
        "category": "資料不足型",
        "question": "Regulation_FAKE000000 相關會議項目有哪些？",
        "terms": ["Regulation_FAKE000000"],
    },
]


def normalize(value) -> str:
    if value is None:
        return ""
    return str(value)


def contains_term(text: str, term: str) -> bool:
    # Short all-capital regulation tokens should match as standalone tokens.
    if term in {"CE", "FDA", "TFDA", "HA"}:
        return bool(re.search(rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])", text, flags=re.IGNORECASE))
    return term.lower() in text.lower()


def item_text(item: dict, meeting: dict | None) -> str:
    fields = [
        item.get("item_id"),
        item.get("item_no"),
        item.get("content"),
        item.get("owner"),
        item.get("planned_date"),
        item.get("actual_completed_date"),
        item.get("tracking_result"),
        item.get("raw_row_text"),
    ]
    if meeting:
        fields.extend(
            [
                meeting.get("meeting_id"),
                meeting.get("meeting_name"),
                meeting.get("meeting_date"),
                meeting.get("responsible_unit"),
                meeting.get("chairperson"),
                meeting.get("recorder"),
            ]
        )
    return "\n".join(normalize(field) for field in fields)


def search_case(case: dict, items: list[dict], meetings_by_id: dict[str, dict]) -> dict:
    rows = []
    for item in items:
        text = item_text(item, meetings_by_id.get(item.get("meeting_id")))
        matched_terms = [term for term in case["terms"] if contains_term(text, term)]
        if not matched_terms:
            continue
        rows.append(
            {
                "score": len(set(matched_terms)),
                "matched_terms": matched_terms,
                "meeting_id": item.get("meeting_id"),
                "item_id": item.get("item_id"),
                "item_no": item.get("item_no"),
                "owner": item.get("owner"),
                "planned_date": normalize(item.get("planned_date")) or None,
                "actual_completed_date": normalize(item.get("actual_completed_date")) or None,
                "content": item.get("content"),
            }
        )
    rows.sort(key=lambda row: (-row["score"], row.get("meeting_id") or "", row.get("item_no") or ""))
    return {
        "category": case["category"],
        "question": case["question"],
        "terms": case["terms"],
        "result_count": len(rows),
        "top1_item_id": rows[0]["item_id"] if rows else None,
        "top1_item_no": rows[0]["item_no"] if rows else None,
        "top1_content": rows[0]["content"] if rows else None,
        "top5_item_ids": [row["item_id"] for row in rows[:5]],
        "results": rows[:10],
    }


def main() -> None:
    setup_django()
    from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection

    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}

    rows = [search_case(case, items, meetings_by_id) for case in CASES]
    summary = {}
    for category in dict.fromkeys(case["category"] for case in CASES):
        subset = [row for row in rows if row["category"] == category]
        summary[category] = {
            "questions": len(subset),
            "has_keyword_results": sum(1 for row in subset if row["result_count"] > 0),
            "empty_results": sum(1 for row in subset if row["result_count"] == 0),
        }

    payload = {
        "description": "Keyword baseline over MongoDB meeting_items and meeting metadata for the same 18 GraphRAG questions.",
        "search_scope": "MongoDB meeting_items fields plus meeting metadata; no Neo4j graph expansion and no vector similarity.",
        "summary": summary,
        "rows": rows,
    }
    out = BASE / "keyword_baseline_18q_0625.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(out)
    for category, data in summary.items():
        print(category, data)
    for i, row in enumerate(rows, 1):
        print(f"{i}. {row['category']} | count={row['result_count']} | {row['question']} | {row['top1_item_id']}")


if __name__ == "__main__":
    main()
