from __future__ import annotations

import re


BLANK_VALUES = {"", "-", "--", "na", "n/a", "none", "null"}
COMPLETED_TERMS = (
    "已完成",
    "結案",
    "closed",
    "completed",
    "done",
    "resolved",
)
HIGH_CONFIDENCE_COMPLETED_PATTERNS = (
    "確認已完成",
    "確認完成",
    "已完成",
    "完成，詳",
    "完成,詳",
    "完成詳",
)
IN_PROGRESS_TERMS = (
    "進行中",
    "處理中",
    "確認中",
    "追蹤中",
    "待確認",
    "pending",
    "in progress",
    "ongoing",
    "follow up",
)
NOT_APPLICABLE_TERMS = (
    "不適用",
    "not applicable",
    "n/a",
    "na",
)


def classify_item_status(item: dict) -> dict:
    completed_date = clean_text(item.get("actual_completed_date"))
    tracking = clean_text(item.get("tracking_result")).lower()
    if is_meaningful_value(completed_date):
        return {"status": "completed", "source": "actual_completed_date", "confidence": "high"}
    if is_not_applicable_tracking(tracking):
        return {"status": "not_applicable", "source": "tracking_result", "confidence": "high"}
    if is_high_confidence_completed_tracking(tracking):
        return {"status": "completed", "source": "tracking_result", "confidence": "high"}
    if contains_any(tracking, IN_PROGRESS_TERMS):
        return {"status": "in_progress", "source": "tracking_result", "confidence": "medium"}
    return {"status": "pending", "source": "", "confidence": "low"}


def is_meaningful_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = normalize_placeholder_value(value)
        return bool(text) and text not in BLANK_VALUES
    return True


def is_high_confidence_completed_tracking(text: str) -> bool:
    normalized = normalize_status_text(text)
    if is_not_applicable_tracking(normalized):
        return False
    if any(pattern in normalized for pattern in HIGH_CONFIDENCE_COMPLETED_PATTERNS):
        return True
    return contains_any(normalized, COMPLETED_TERMS)


def is_not_applicable_tracking(text: str) -> bool:
    normalized = normalize_status_text(text)
    return normalize_placeholder_value(normalized) in {"-", "--"} or contains_any(normalized, NOT_APPLICABLE_TERMS)


def normalize_placeholder_value(value: str) -> str:
    text = str(value or "").strip().lower().translate(str.maketrans({"－": "-", "–": "-", "—": "-"}))
    return re.sub(r"\s+", "", text)


def normalize_status_text(text: str) -> str:
    value = str(text or "").lower()
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(term.lower() in lowered for term in terms)


def clean_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())
