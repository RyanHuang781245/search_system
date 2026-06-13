from __future__ import annotations

import json
import math
import re

from django.conf import settings


REGULATION_KEYWORDS = {"FDA", "TFDA", "CFDA", "CE", "PMDA"}
PRODUCT_CUES = {
    "stem",
    "handle",
    "head",
    "cup",
    "coating",
    "rasp",
    "remover",
    "inserter",
    "impactor",
    "system",
    "implant",
    "instrument",
}
STOPWORDS = {
    "and",
    "the",
    "with",
    "for",
    "type",
    "meeting",
    "minutes",
    "record",
    "review",
    "risk",
    "requires",
    "require",
    "evaluation",
    "na",
    "n/a",
    "none",
    "null",
}
JIEBA_ALLOWED_POS = ("n", "nz", "eng", "vn")
SUPPORTED_LLM_TYPES = {
    "regulation",
    "abbreviation",
    "product",
    "technical_term",
    "task_term",
    "english_phrase",
    "mixed_term",
    "chinese_term",
    "domain_term",
}


def extract_keyword_entities(
    text: str | None,
    max_keywords: int = 12,
    llm_client=None,
    embedder=None,
) -> dict:
    source = normalize_source(text)
    candidates = {}

    add_regex_candidates(source, candidates)
    jieba_available = add_jieba_candidates(source, candidates)
    if not jieba_available:
        add_chinese_ngram_candidates(source, candidates)

    if keyword_llm_enabled():
        add_llm_candidates(source, candidates, max_keywords=max_keywords, llm_client=llm_client)

    if keyword_embedding_rerank_enabled():
        rerank_candidates_with_embeddings(source, candidates, embedder=embedder)

    keywords = sorted(candidates.values(), key=lambda item: (-item["score"], item["name"].lower()))
    keywords = keywords[:max_keywords]

    products = [
        item["name"]
        for item in keywords
        if item["type"] == "product" and (" " in item["name"] or "ollama_llm" in item["method"])
    ]
    regulations = [item["name"] for item in keywords if item["name"].upper() in REGULATION_KEYWORDS]

    return {
        "keywords": keywords,
        "products": dedupe(products),
        "regulations": dedupe(regulations),
    }


def add_regex_candidates(source: str, candidates: dict) -> None:
    for match in re.finditer(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9/-]{1,})(?![A-Za-z0-9])", source):
        token = match.group(1)
        if is_valid_keyword(token):
            add_candidate(candidates, token, infer_keyword_type(token), 0.74, "regex_abbreviation")

    phrase_pattern = re.compile(
        r"(?<![A-Za-z0-9])([A-Za-z][A-Za-z0-9-]+(?:\s+[A-Za-z][A-Za-z0-9-]+){1,4})(?![A-Za-z0-9])"
    )
    for match in phrase_pattern.finditer(source):
        phrase = normalize_phrase(match.group(1))
        if is_valid_keyword(phrase):
            add_candidate(candidates, phrase, infer_keyword_type(phrase), 0.7, "regex_phrase")

    add_product_phrase_candidates(source, candidates)


def add_product_phrase_candidates(source: str, candidates: dict) -> None:
    for segment in re.findall(r"[A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){1,8}", source):
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]*", segment)
        for index, token in enumerate(tokens):
            if token.lower() not in PRODUCT_CUES:
                continue
            for start in range(max(0, index - 2), index):
                phrase = normalize_phrase(" ".join(tokens[start : index + 1]))
                if is_valid_keyword(phrase):
                    add_candidate(candidates, phrase, "product", 0.76, "regex_product_phrase")


def add_jieba_candidates(source: str, candidates: dict) -> bool:
    try:
        import jieba.analyse
    except Exception:
        return False

    for term, weight in jieba.analyse.extract_tags(
        source,
        topK=24,
        withWeight=True,
        allowPOS=JIEBA_ALLOWED_POS,
    ):
        term = normalize_phrase(term)
        if is_valid_keyword(term):
            add_candidate(candidates, term, infer_keyword_type(term), normalize_weight(weight, 0.72), "jieba_tfidf")

    try:
        textrank_terms = jieba.analyse.textrank(
            source,
            topK=24,
            withWeight=True,
            allowPOS=JIEBA_ALLOWED_POS,
        )
    except Exception:
        textrank_terms = []

    for term, weight in textrank_terms:
        term = normalize_phrase(term)
        if is_valid_keyword(term):
            add_candidate(candidates, term, infer_keyword_type(term), normalize_weight(weight, 0.68), "jieba_textrank")
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
                    add_candidate(candidates, token, infer_keyword_type(token), 0.38, "cjk_ngram")


def add_llm_candidates(source: str, candidates: dict, max_keywords: int, llm_client=None) -> None:
    if not source:
        return

    try:
        payload = (llm_client or ollama_keyword_candidates)(source, max_keywords=max(max_keywords, 12))
    except Exception:
        return

    for item in payload:
        if isinstance(item, str):
            name = item
            keyword_type = infer_keyword_type(item)
            score = 0.8
        else:
            name = item.get("name")
            keyword_type = normalize_llm_type(item.get("type"), name)
            score = item.get("score", 0.82)
        add_candidate(candidates, name, keyword_type, score, "ollama_llm")


def ollama_keyword_candidates(source: str, max_keywords: int = 12) -> list[dict]:
    try:
        import requests
    except Exception:
        return []

    url = f"http://{get_setting('OLLAMA_HOST', 'localhost')}:{get_setting('OLLAMA_PORT', 11434)}/api/chat"
    content = source[: int(get_setting("KEYWORD_LLM_MAX_INPUT_CHARS", 1800))]
    prompt = (
        "Extract important keywords from this enterprise meeting record item.\n"
        "Focus on newly appearing product names, technical terms, regulations, document tasks, risks, owners' units, "
        "and internal codes. Do not rely on any predefined keyword list.\n"
        "Return JSON only with this shape:\n"
        '{"keywords":[{"name":"keyword","type":"product|regulation|abbreviation|technical_term|task_term|english_phrase|mixed_term|chinese_term","score":0.0}]}\n'
        f"Return at most {max_keywords} keywords.\n\n"
        f"Text:\n{content}"
    )

    response = requests.post(
        url,
        json={
            "model": get_setting("OLLAMA_INFERENCE_MODEL", "qwen2.5:3b"),
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=int(get_setting("KEYWORD_LLM_TIMEOUT", 45)),
    )
    response.raise_for_status()
    payload = response.json()
    content = payload.get("message", {}).get("content", "")
    data = parse_llm_json(content)
    keywords = data.get("keywords", []) if isinstance(data, dict) else []
    if not isinstance(keywords, list):
        return []
    return keywords[:max_keywords]


def parse_llm_json(content: str) -> dict:
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}


def rerank_candidates_with_embeddings(source: str, candidates: dict, embedder=None) -> None:
    if not source or not candidates:
        return

    ranked_items = sorted(candidates.values(), key=lambda item: -item["score"])
    limit = int(get_setting("KEYWORD_EMBEDDING_RERANK_LIMIT", 18))
    ranked_items = ranked_items[:limit]

    try:
        embedding_fn = embedder or get_default_embedder()
        source_vector = embedding_fn(source[: int(get_setting("KEYWORD_EMBEDDING_MAX_INPUT_CHARS", 1800))])
    except Exception:
        return

    for item in ranked_items:
        try:
            keyword_vector = embedding_fn(item["name"])
            similarity = cosine_similarity(source_vector, keyword_vector)
        except Exception:
            continue

        old_score = float(item.get("score", 0))
        blended_score = (old_score * 0.65) + (similarity * 0.35)
        item["score"] = round(max(old_score, min(blended_score, 0.98)), 4)
        if "embedding_rerank" not in item["method"].split("+"):
            item["method"] = f"{item['method']}+embedding_rerank"


def get_default_embedder():
    return ollama_keyword_embedding


def ollama_keyword_embedding(text: str) -> list[float]:
    try:
        import requests
    except Exception:
        return []

    url = f"http://{get_setting('OLLAMA_HOST', 'localhost')}:{get_setting('OLLAMA_PORT', 11434)}/api/embeddings"
    response = requests.post(
        url,
        json={"model": get_setting("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text"), "prompt": text},
        timeout=int(get_setting("KEYWORD_EMBEDDING_TIMEOUT", 10)),
    )
    response.raise_for_status()
    payload = response.json()
    vector = payload.get("embedding")
    return vector if isinstance(vector, list) else []


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(min(dot / (left_norm * right_norm), 1.0), -1.0)


def add_candidate(candidates: dict, name: str | None, keyword_type: str, score: float, method: str) -> None:
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


def normalize_phrase(value: str | None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:()[]{}<>\"'")
    return text


def normalize_weight(weight: float, cap: float) -> float:
    try:
        weight = float(weight)
    except (TypeError, ValueError):
        return 0.5
    if weight <= 0:
        return 0.5
    return min(round(weight / (weight + 1), 4), cap)


def normalize_llm_type(keyword_type: str | None, name: str | None) -> str:
    normalized_type = str(keyword_type or "").strip().lower()
    if normalized_type in SUPPORTED_LLM_TYPES:
        return normalized_type
    return infer_keyword_type(str(name or ""))


def infer_keyword_type(term: str) -> str:
    upper = term.upper()
    if upper in REGULATION_KEYWORDS:
        return "regulation"
    if re.fullmatch(r"[A-Z][A-Z0-9/-]{1,}", term):
        return "abbreviation"
    if re.search(r"[A-Za-z]", term) and has_product_cue(term) and len(english_tokens(term)) <= 4:
        return "product"
    if re.search(r"[A-Za-z]", term) and re.search(r"[\u3400-\u9fff]", term):
        return "mixed_term"
    if re.search(r"[A-Za-z]", term):
        return "english_phrase"
    return "chinese_term"


def has_product_cue(term: str) -> bool:
    tokens = {token.lower() for token in english_tokens(term)}
    return bool(tokens & PRODUCT_CUES)


def english_tokens(term: str) -> list[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9-]*", term)


def is_valid_keyword(term: str) -> bool:
    if not term:
        return False
    normalized = term.strip().lower()
    if normalized in STOPWORDS:
        return False
    if len(normalized) < 2 or len(normalized) > 80:
        return False
    if normalized.isdigit():
        return False
    if re.fullmatch(r"[-_/.,;:()\s]+", normalized):
        return False
    return True


def keyword_llm_enabled() -> bool:
    return bool(get_setting("KEYWORD_LLM_ENABLED", True))


def keyword_embedding_rerank_enabled() -> bool:
    return bool(get_setting("KEYWORD_EMBEDDING_RERANK_ENABLED", True))


def get_setting(name: str, default):
    try:
        return getattr(settings, name, default)
    except Exception:
        return default


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
