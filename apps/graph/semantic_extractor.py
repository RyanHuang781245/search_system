from __future__ import annotations

import hashlib
import re

from .keyword_extractor import extract_keyword_entities


COMPLETED_TERMS = (
    "已完成",
    "完成",
    "結案",
    "closed",
    "complete",
    "completed",
    "done",
    "resolved",
)
IN_PROGRESS_TERMS = (
    "進行中",
    "處理中",
    "確認中",
    "追蹤中",
    "pending",
    "in progress",
    "ongoing",
    "follow up",
)
DECISION_TERMS = (
    "決議",
    "決定",
    "同意",
    "核准",
    "確認採用",
    "決定採用",
    "approved",
    "decided",
    "agreed",
)
RISK_TERMS = (
    "風險",
    "問題",
    "異常",
    "不一致",
    "延遲",
    "延後",
    "影響",
    "待確認",
    "需確認",
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
        "products": keywords.get("products", []),
        "regulations": keywords.get("regulations", []),
        "keywords": [keyword["name"] for keyword in keywords.get("keywords", [])],
    }


def build_action_descriptor(item: dict, text: str) -> dict:
    item_id = item.get("item_id")
    return {
        "action_id": f"action_{item_id}",
        "title": truncate_text(text or item_id, 96),
        "status": detect_status(item),
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


def detect_status(item: dict) -> str:
    completed_date = _clean_text(item.get("actual_completed_date"))
    tracking = _clean_text(item.get("tracking_result")).lower()
    if completed_date or contains_any(tracking, COMPLETED_TERMS):
        return "completed"
    if contains_any(tracking, IN_PROGRESS_TERMS):
        return "in_progress"
    return "pending"


def infer_risk_severity(text: str) -> str:
    lowered = str(text or "").lower()
    if any(term in lowered for term in ("重大", "嚴重", "critical", "blocker", "high risk")):
        return "high"
    if any(term in lowered for term in ("低", "minor", "low risk")):
        return "low"
    return "medium"


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in terms)


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
    text = _clean_text(value)
    return bool(text and text.lower() not in {"--", "na", "n/a", "none", "null"})
