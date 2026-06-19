from __future__ import annotations

import hashlib
import re

from apps.item_status import contains_any, is_meaningful_value, item_status_payload

from .keyword_extractor import dedupe, extract_keyword_entities, valid_person_name


DECISION_TERMS = (
    "\u6c7a\u8b70",
    "\u6c7a\u5b9a",
    "\u540c\u610f",
    "\u6838\u51c6",
    "\u78ba\u8a8d\u63a1\u7528",
    "\u6c7a\u5b9a\u63a1\u7528",
    "approved",
    "decided",
    "agreed",
)
RISK_TERMS = (
    "\u98a8\u96aa",
    "\u554f\u984c",
    "\u7570\u5e38",
    "\u4e0d\u4e00\u81f4",
    "\u5ef6\u9072",
    "\u5ef6\u5f8c",
    "\u5f71\u97ff",
    "\u5f85\u78ba\u8a8d",
    "\u9700\u78ba\u8a8d",
    "risk",
    "issue",
    "concern",
    "delay",
    "inconsistent",
    "impingement",
)


def extract_semantic_item(item: dict) -> dict:
    content = _clean_text(item.get("content"))
    tracking = _clean_text(item.get("tracking_result"))
    combined = " ".join(value for value in (content, tracking) if value)
    keywords = extract_keyword_entities(combined) if combined else {"keywords": [], "products": [], "regulations": []}
    issue = build_issue_descriptor(item, keywords, combined)
    action = build_action_descriptor(item, combined) if content or _valid_text(item.get("owner")) else None
    decision = build_decision_descriptor(item, combined) if contains_any(combined, DECISION_TERMS) else None
    risk = build_risk_descriptor(item, combined) if contains_any(combined, RISK_TERMS) else None
    return {
        "action": action,
        "decision": decision,
        "risk": risk,
        "issue": issue,
        "responsible_people": extract_responsible_people_from_text(combined),
        "products": keywords.get("products", []),
        "regulations": keywords.get("regulations", []),
        "keywords": [keyword["name"] for keyword in keywords.get("keywords", [])],
    }


def build_action_descriptor(item: dict, text: str) -> dict:
    item_id = item.get("item_id")
    status_payload = detect_status(item)
    return {
        "action_id": f"action_{item_id}",
        "title": truncate_text(text or item_id, 96),
        "status": status_payload["status"],
        "status_source": status_payload["source"],
        "status_confidence": status_payload["confidence"],
        "content": _clean_text(item.get("content")),
        "tracking_result": _clean_text(item.get("tracking_result")),
        "planned_date": _clean_text(item.get("planned_date")),
        "actual_completed_date": _clean_text(item.get("actual_completed_date")),
    }


def build_decision_descriptor(item: dict, text: str) -> dict:
    item_id = item.get("item_id")
    return {
        "decision_id": f"decision_{item_id}",
        "title": truncate_text(text or item_id, 96),
        "evidence": text,
    }


def build_risk_descriptor(item: dict, text: str) -> dict:
    item_id = item.get("item_id")
    return {
        "risk_id": f"risk_{item_id}",
        "name": truncate_text(text or item_id, 96),
        "evidence": text,
        "severity": infer_risk_severity(text),
    }


def build_issue_descriptor(item: dict, keywords: dict, text: str) -> dict | None:
    if not text:
        return None
    products = keywords.get("products", [])
    regulations = keywords.get("regulations", [])
    keyword_names = [keyword["name"] for keyword in keywords.get("keywords", [])]
    core_anchors = [*products, *regulations]
    anchors = core_anchors or keyword_names[:3]
    if anchors:
        signature = "|".join(sorted({normalize_signature(anchor) for anchor in anchors if anchor}))
        title = " / ".join(anchors[:3])
    else:
        signature = normalize_signature(text)[:80]
        title = truncate_text(text, 72)
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return {
        "issue_id": f"issue_{digest}",
        "title": title or item.get("item_id") or digest,
        "signature": signature,
    }


def detect_status(item: dict) -> dict:
    return item_status_payload(item)


def infer_risk_severity(text: str) -> str:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ("\u91cd\u5927", "\u56b4\u91cd", "critical", "blocker", "high risk")):
        return "high"
    if any(term in lowered for term in ("\u4f4e", "minor", "low risk")):
        return "low"
    return "medium"


def extract_responsible_people_from_text(text: str) -> list[str]:
    source = _clean_text(text)
    if not source:
        return []

    candidates = []
    patterns = (
        (
            r"(?:\u539f?\s*\u8ca0\s*\u8cac\s*\u4eba|owner|responsible)"
            r"[^。\uff1b;,.，]*?"
            r"(?:\u6539\s*[\u70ba\u7232\u4eba]|\u66f4\s*\u6539\s*[\u70ba\u7232\u4eba]|"
            r"\u8b8a\s*\u66f4\s*[\u70ba\u7232\u4eba]|changed\s+to|change\s+to)"
            r"\s*([^。\uff1b;,.，()\uff08\uff09]+)"
        ),
        (
            r"(?:\u6539\s*\u7531|\u7531)\s*([^。\uff1b;,.，()\uff08\uff09]{2,40}?)"
            r"(?:\u8ca0\s*\u8cac|\u8655\s*\u7406|\u78ba\s*\u8a8d|\u5354\s*\u52a9)"
        ),
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source, flags=re.I):
            candidates.extend(split_person_candidates(match.group(1)))
    return dedupe([name for name in candidates if valid_person_name(name)])


def split_person_candidates(value: str) -> list[str]:
    parts = re.split(r"[\u3001/,，\u8207\u548c]| and ", str(value or ""), flags=re.I)
    return [normalize_person_candidate(part) for part in parts if normalize_person_candidate(part)]


def normalize_person_candidate(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"^(\u539f)?\u8ca0\s*\u8cac\s*\u4eba", "", text)
    text = re.sub(r"(\u8ca0\s*\u8cac|\u8655\s*\u7406|\u78ba\s*\u8a8d|\u5354\s*\u52a9).*$", "", text)
    return text.strip(" :\uff1a-()\uff08\uff09[]{}")


def normalize_signature(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff ]+", "", text)
    return text


def truncate_text(value: str, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def _clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _valid_text(value) -> bool:
    return is_meaningful_value(_clean_text(value))
