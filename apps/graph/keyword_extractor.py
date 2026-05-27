from __future__ import annotations

import re


ABBREVIATION_KEYWORDS = ["FDA", "TFDA", "CFDA", "CE", "PMDA", "UPD", "UR3", "UR4"]
PRODUCT_TERMS = [
    "Conformity stem",
    "Short neck",
    "Modular handle",
    "Metal head",
    "Ceramic head",
    "Centralizer",
    "Restrictor",
    "Broach",
]
CHINESE_KEYWORDS = [
    "認證",
    "送件",
    "法規",
    "標籤",
    "包裝",
    "測試",
    "導量產",
    "品號",
    "產品名稱",
    "器械",
    "開發時程",
    "競品",
    "申請地區",
]
REGULATION_KEYWORDS = {"FDA", "TFDA", "CFDA", "CE", "PMDA"}


def extract_keyword_entities(text: str | None) -> dict:
    source = str(text or "")
    found_keywords = []
    found_products = []
    found_regulations = []

    for token in ABBREVIATION_KEYWORDS:
        if _contains_term(source, token):
            found_keywords.append({"name": token, "type": "abbreviation"})
            if token in REGULATION_KEYWORDS:
                found_regulations.append(token)

    for token in PRODUCT_TERMS:
        if _contains_phrase(source, token):
            found_keywords.append({"name": token, "type": "product"})
            found_products.append(token)

    for token in CHINESE_KEYWORDS:
        if token in source:
            found_keywords.append({"name": token, "type": "chinese"})

    deduped_keywords = _dedupe_keyword_dicts(found_keywords)
    return {
        "keywords": deduped_keywords,
        "products": _dedupe(found_products),
        "regulations": _dedupe(found_regulations),
    }


def extract_person_names(meeting: dict, item: dict | None = None) -> list[str]:
    names = []
    for field in ("chairperson", "recorder", "owner"):
        if field == "owner" and item is None:
            continue
        source = item if field == "owner" and item is not None else meeting
        name = str(source.get(field) or "").strip()
        if _valid_person_name(name):
            names.append(name)

    attendees = meeting.get("attendees") or []
    if isinstance(attendees, list):
        for attendee in attendees:
            attendee_name = str(attendee or "").strip()
            if _valid_person_name(attendee_name):
                names.append(attendee_name)

    return _dedupe(names)


def _contains_term(text: str, token: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", re.IGNORECASE)
    return pattern.search(text) is not None


def _contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_keyword_dicts(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        key = (item["name"], item["type"])
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _valid_person_name(name: str) -> bool:
    lowered = name.lower()
    return bool(name) and lowered not in {"--", "na", "n/a", "none", "null"}
