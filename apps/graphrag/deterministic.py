from __future__ import annotations

import re


REGULATION_PATTERN = re.compile(r"\b(FDA|TFDA|CFDA|PMDA|CE|ISO\s*\d*)\b", flags=re.I)
DATE_PATTERNS = (
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(?:(\d{1,2})\s*日)?"),
    re.compile(r"(\d{4})\s*[-/]\s*(\d{1,2})(?:\s*[-/]\s*(\d{1,2}))?"),
)
PRODUCT_TERMS = (
    "Conformity stem",
    "Short neck",
    "Locking cage",
    "Modular handle",
    "Aio Modular handle",
    "P1812",
    "HA-Fit",
    "stem",
    "cage",
    "handle",
)
STATUS_TERMS = {
    "not_completed": ("未完成", "尚未", "沒完成", "未結案", "open", "not completed"),
    "not_applicable": ("不適用", "不需", "無需", "not applicable", "n/a"),
    "completed": ("已完成", "實際完成", "完成日期", "完成了", "closed", "done", "completed"),
    "in_progress": ("進行中", "處理中", "pending", "ongoing", "in progress"),
}
PSEUDONYM_PERSON_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(Person_[A-F0-9]{10})(?![A-Za-z0-9_])", flags=re.I)


def deterministic_query_understanding(question: str) -> dict:
    text = str(question or "").strip()
    lowered = text.lower()
    entities = {
        "meeting_hint": extract_meeting_hint(text),
        "person_name": extract_person_name(text),
        "unit_name": extract_unit_name(text),
        "date_value": extract_date_value(text),
        "product_name": extract_product_name(text),
        "regulation_name": extract_regulation_name(text),
        "status": extract_status(text),
        "keyword": "",
    }
    graph_intent = determine_graph_intent(text, lowered, entities)
    return {
        "query_type": determine_query_type(text, lowered, entities, graph_intent),
        "graph_intent": graph_intent,
        "entities": entities,
    }


def determine_query_type(text: str, lowered: str, entities: dict, graph_intent: str) -> str:
    if is_follow_up_tracking_question(lowered):
        return "follow_up_tracking"
    if graph_intent in {"person_attendance", "meeting_chair", "meeting_recorder", "unit_meetings"}:
        return "relation_lookup"
    constraints = sum(
        bool(entities.get(key))
        for key in ("person_name", "date_value", "product_name", "regulation_name", "status")
    )
    if constraints >= 2 and has_item_scope(lowered):
        return "composite_query"
    if entities.get("status") and has_item_scope(lowered):
        return "composite_query"
    if graph_intent == "person_responsibility" and (
        entities.get("person_name") or has_any(lowered, ("負責", "誰負責", "responsible"))
    ):
        return "relation_lookup"
    if is_structural_item_list_question(lowered):
        return "structural_list"
    if is_meeting_summary_question(lowered, entities):
        return "meeting_summary"
    if is_semantic_summary_question(lowered):
        return "semantic_summary"
    if graph_intent != "keyword_related":
        return "relation_lookup"
    if is_keyword_exploration_question(text, lowered, entities):
        return "keyword_exploration"
    return "open_qa"


def determine_graph_intent(text: str, lowered: str, entities: dict) -> str:
    if entities.get("date_value"):
        if has_any(lowered, ("實際完成", "已完成", "完成日期", "actual completed", "closed", "done")):
            return "completed_date"
        return "planned_date"
    if has_any(lowered, ("出席", "參加", "attended", "attendance")):
        return "person_attendance"
    if has_any(lowered, ("主持", "chair", "chaired")):
        return "meeting_chair"
    if has_any(lowered, ("記錄", "紀錄", "recorder", "recorded")):
        return "meeting_recorder"
    if has_any(lowered, ("單位", "部門", "unit", "department")) or entities.get("unit_name"):
        return "unit_meetings"
    if entities.get("person_name") and has_item_scope(lowered):
        return "person_responsibility"
    if has_any(lowered, ("負責", "誰負責", "owner", "responsible")) or is_probable_person_name(text):
        return "person_responsibility"
    if entities.get("product_name"):
        return "product_related"
    if entities.get("regulation_name"):
        return "regulation_related"
    return "keyword_related"


def is_structural_item_list_question(text: str) -> bool:
    return has_any(text, ("會議", "meeting")) and has_any(
        text,
        (
            "項目",
            "事項",
            "討論事項",
            "議題",
            "item",
            "agenda",
            "topic",
            "內容",
            "包含",
            "列出",
        ),
    )


def is_semantic_summary_question(text: str) -> bool:
    return has_any(
        text,
        (
            "風險",
            "決議",
            "決定",
            "追蹤",
            "問題",
            "摘要",
            "整理",
            "risk",
            "decision",
            "follow-up",
            "follow up",
            "issue",
            "summary",
        ),
    )


def is_follow_up_tracking_question(text: str) -> bool:
    return has_any(
        text,
        (
            "跨會議追蹤",
            "追蹤事項",
            "後續追蹤",
            "後續狀況",
            "後來怎麼處理",
            "後來如何處理",
            "演變",
            "issue tracking",
            "follow-up tracking",
            "follow up tracking",
        ),
    )


def is_meeting_summary_question(text: str, entities: dict) -> bool:
    return bool(entities.get("meeting_hint")) and has_any(
        text,
        ("摘要", "整理", "重點", "summary", "summarize"),
    )


def is_keyword_exploration_question(text: str, lowered: str, entities: dict) -> bool:
    return bool(entities.get("regulation_name") or entities.get("product_name")) or has_any(
        lowered,
        ("相關", "提到", "關於", "related", "mentions", "about"),
    )


def has_item_scope(text: str) -> bool:
    return has_any(text, ("項目", "事項", "item", "items", "待辦", "action", "負責", "完成", "相關", "適用"))


def extract_date_value(text: str) -> str:
    value = str(text or "")
    for pattern in DATE_PATTERNS:
        match = pattern.search(value)
        if not match:
            continue
        year, month, day = match.groups()
        if day:
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
        return f"{int(year):04d}-{int(month):02d}"
    return ""


def contains_date(text: str) -> bool:
    return bool(extract_date_value(text))


def extract_regulation_name(text: str) -> str:
    match = REGULATION_PATTERN.search(str(text or ""))
    return match.group(1).strip() if match else ""


def contains_regulation(text: str) -> bool:
    return bool(extract_regulation_name(text))


def extract_product_name(text: str) -> str:
    value = str(text or "")
    lowered = value.lower()
    matches = [term for term in PRODUCT_TERMS if term.lower() in lowered]
    if not matches:
        return ""
    return sorted(matches, key=len, reverse=True)[0]


def extract_status(text: str) -> str:
    lowered = str(text or "").lower()
    for status, terms in STATUS_TERMS.items():
        if has_any(lowered, terms):
            return status
    return ""


def extract_person_name(text: str) -> str:
    value = str(text or "").strip()
    pseudonym_match = PSEUDONYM_PERSON_PATTERN.search(value)
    if pseudonym_match:
        return normalize_pseudonym_person(pseudonym_match.group(1))
    if is_probable_person_name(value):
        return value
    match = re.search(r"([\u4e00-\u9fff]{2,4})(?:負責|出席|參加|主持|記錄|紀錄)", value)
    if match:
        return match.group(1)
    match = re.search(r"\b([A-Za-z][A-Za-z0-9_-]{1,})\s*(?:負責|出席|參加|主持|記錄|紀錄)", value)
    if match:
        candidate = match.group(1).strip()
        if not is_question_placeholder(candidate):
            return candidate
    match = re.search(r"^([\u4e00-\u9fff]{2,4})(?=\s|,|，|FDA|TFDA|CFDA|PMDA|CE|Conformity|stem|cage|handle|未完成|已完成|負責|出席|主持|記錄|紀錄)", value, flags=re.I)
    if match:
        return match.group(1)
    match = re.search(r"\b(?:is|what is|what's)?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:responsible|owner|attended|chair|chaired|recorder|recorded)\b", value, flags=re.I)
    if match:
        candidate = match.group(1).strip()
        if candidate.lower() not in {"which", "what", "item", "items", "included", "included in"}:
            return candidate
    return ""


def is_question_placeholder(value: str) -> bool:
    return str(value or "").strip().lower() in {
        "who",
        "what",
        "which",
        "whose",
        "item",
        "items",
        "owner",
        "responsible",
    }


def extract_unit_name(text: str) -> str:
    match = re.search(r"\b(UR\d+|UPD|QA|RA|RD|業務|法規)\b", str(text or ""), flags=re.I)
    return match.group(1).strip() if match else ""


def extract_meeting_hint(text: str) -> str:
    value = str(text or "").strip()
    if "會議" not in value and "meeting" not in value.lower():
        return ""
    cleaned = re.sub(r"(包含|有哪些|哪些|列出|討論事項|事項|項目|議題|內容|摘要|整理|重點|summary|summarize|meeting|會議)", " ", value, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def is_probable_person_name(text: str) -> bool:
    value = str(text or "").strip()
    if not value or contains_regulation(value) or contains_date(value):
        return False
    if PSEUDONYM_PERSON_PATTERN.fullmatch(value):
        return True
    if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", value):
        return True
    if re.fullmatch(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?", value):
        return True
    return False


def normalize_pseudonym_person(value: str) -> str:
    prefix, digest = str(value or "").split("_", 1)
    return f"{prefix[:1].upper()}{prefix[1:].lower()}_{digest.upper()}"


def has_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)
