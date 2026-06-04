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
CHINESE_SEED_KEYWORDS = [
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
STOPWORDS = {
    "and",
    "the",
    "with",
    "for",
    "type",
    "meeting",
    "minutes",
    "record",
    "na",
    "n/a",
    "none",
    "null",
    "請",
    "確認",
    "建議",
    "進行",
    "提供",
    "相關",
    "以下",
    "是否",
    "需要",
    "目前",
    "後續",
    "會議",
    "專案",
    "產品",
}
JIEBA_ALLOWED_POS = ("n", "nz", "eng", "vn")


def extract_keyword_entities(text: str | None, max_keywords: int = 12) -> dict:
    source = normalize_source(text)
    candidates = {}

    add_domain_candidates(source, candidates)
    add_regex_candidates(source, candidates)
    jieba_available = add_jieba_candidates(source, candidates)
    if not jieba_available:
        add_chinese_ngram_candidates(source, candidates)

    keywords = sorted(candidates.values(), key=lambda item: (-item["score"], item["name"].lower()))
    keywords = keywords[:max_keywords]

    products = [
        item["name"]
        for item in keywords
        if item["type"] == "product" or item["name"].lower() in {term.lower() for term in PRODUCT_TERMS}
    ]
    regulations = [item["name"] for item in keywords if item["name"].upper() in REGULATION_KEYWORDS]

    return {
        "keywords": keywords,
        "products": dedupe(products),
        "regulations": dedupe(regulations),
    }


def add_domain_candidates(source: str, candidates: dict) -> None:
    for token in ABBREVIATION_KEYWORDS:
        if contains_term(source, token):
            keyword_type = "regulation" if token in REGULATION_KEYWORDS else "abbreviation"
            add_candidate(candidates, token, keyword_type, 1.0, "domain_abbreviation")

    for token in PRODUCT_TERMS:
        if contains_phrase(source, token):
            add_candidate(candidates, token, "product", 0.96, "domain_product")

    for token in CHINESE_SEED_KEYWORDS:
        if token in source:
            add_candidate(candidates, token, "domain_term", 0.92, "domain_chinese")


def add_regex_candidates(source: str, candidates: dict) -> None:
    for match in re.finditer(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9/-]{1,})(?![A-Za-z0-9])", source):
        token = match.group(1)
        if is_valid_keyword(token):
            keyword_type = "regulation" if token in REGULATION_KEYWORDS else "abbreviation"
            add_candidate(candidates, token, keyword_type, 0.88, "regex_abbreviation")

    phrase_pattern = re.compile(
        r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9-]+(?:\s+[A-Za-z][A-Za-z0-9-]+){1,3})(?![A-Za-z0-9])"
    )
    for match in phrase_pattern.finditer(source):
        phrase = normalize_phrase(match.group(1))
        if is_valid_keyword(phrase):
            add_candidate(candidates, phrase, infer_keyword_type(phrase), 0.72, "regex_phrase")


def add_jieba_candidates(source: str, candidates: dict) -> bool:
    try:
        import jieba
        import jieba.analyse
    except Exception:
        return False

    for term in [*CHINESE_SEED_KEYWORDS, *PRODUCT_TERMS]:
        jieba.add_word(term)

    for term, weight in jieba.analyse.extract_tags(
        source,
        topK=20,
        withWeight=True,
        allowPOS=JIEBA_ALLOWED_POS,
    ):
        term = normalize_phrase(term)
        if is_valid_keyword(term):
            add_candidate(candidates, term, infer_keyword_type(term), normalize_weight(weight, 0.82), "jieba_tfidf")

    try:
        textrank_terms = jieba.analyse.textrank(
            source,
            topK=20,
            withWeight=True,
            allowPOS=JIEBA_ALLOWED_POS,
        )
    except Exception:
        textrank_terms = []

    for term, weight in textrank_terms:
        term = normalize_phrase(term)
        if is_valid_keyword(term):
            add_candidate(candidates, term, infer_keyword_type(term), normalize_weight(weight, 0.78), "jieba_textrank")
    return True


def add_chinese_ngram_candidates(source: str, candidates: dict) -> None:
    for segment in re.findall(r"[\u3400-\u9fff]{2,12}", source):
        if segment in STOPWORDS:
            continue
        for size in (4, 3, 2):
            if len(segment) < size:
                continue
            for index in range(0, len(segment) - size + 1):
                token = segment[index:index + size]
                if is_valid_keyword(token):
                    add_candidate(candidates, token, infer_keyword_type(token), 0.45, "cjk_ngram")


def add_candidate(candidates: dict, name: str, keyword_type: str, score: float, method: str) -> None:
    normalized_name = normalize_phrase(name)
    if not is_valid_keyword(normalized_name):
        return

    key = normalized_name.lower()
    existing = candidates.get(key)
    score = round(float(score), 4)
    if existing is None or score > existing["score"]:
        candidates[key] = {
            "name": normalized_name,
            "type": keyword_type,
            "score": score,
            "method": method,
        }
        return

    if method not in existing["method"].split("+"):
        existing["method"] = f"{existing['method']}+{method}"


def extract_person_names(meeting: dict, item: dict | None = None) -> list[str]:
    names = []
    for field in ("chairperson", "recorder", "owner"):
        if field == "owner" and item is None:
            continue
        source = item if field == "owner" and item is not None else meeting
        name = str(source.get(field) or "").strip()
        if valid_person_name(name):
            names.append(name)

    attendees = meeting.get("attendees") or []
    if isinstance(attendees, list):
        for attendee in attendees:
            attendee_name = str(attendee or "").strip()
            if valid_person_name(attendee_name):
                names.append(attendee_name)

    return dedupe(names)


def normalize_source(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_phrase(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:()[]{}<>")
    return text


def normalize_weight(weight: float, cap: float) -> float:
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        return 0.5
    if weight <= 0:
        return 0.5
    return min(round(weight / (weight + 1), 4), cap)


def infer_keyword_type(term: str) -> str:
    upper = term.upper()
    if upper in REGULATION_KEYWORDS:
        return "regulation"
    if upper in ABBREVIATION_KEYWORDS or re.fullmatch(r"[A-Z][A-Z0-9/-]{1,}", term):
        return "abbreviation"
    if any(term.lower() == product.lower() for product in PRODUCT_TERMS):
        return "product"
    if re.search(r"[A-Za-z]", term) and re.search(r"[\u3400-\u9fff]", term):
        return "mixed_term"
    if re.search(r"[A-Za-z]", term):
        return "english_phrase"
    return "chinese_term"


def is_valid_keyword(term: str) -> bool:
    if not term:
        return False
    normalized = term.strip().lower()
    if normalized in STOPWORDS:
        return False
    if len(normalized) < 2 or len(normalized) > 60:
        return False
    if normalized.isdigit():
        return False
    if re.fullmatch(r"[-_/.,;:()\s]+", normalized):
        return False
    return True


def contains_term(text: str, token: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", re.IGNORECASE)
    return pattern.search(text) is not None


def contains_phrase(text: str, phrase: str) -> bool:
    return phrase.lower() in text.lower()


def dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def valid_person_name(name: str) -> bool:
    lowered = name.lower()
    return bool(name) and lowered not in {"--", "na", "n/a", "none", "null"}
