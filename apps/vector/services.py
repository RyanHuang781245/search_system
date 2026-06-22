from __future__ import annotations

import re
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings

from apps.item_status import is_meaningful_value, item_status_payload
from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection


class VectorServiceError(Exception):
    """Raised when vector indexing or retrieval cannot be completed."""


PSEUDONYM_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(Person|Unit|Company|File|Ref|Email|Phone|ID|Token)_[A-F0-9]{10}(?![A-Za-z0-9_])")


def index_meeting_items(batch_size: int = 64, client=None, embedder=None) -> dict:
    client = client or get_qdrant_client()
    embedder = embedder or ollama_embedding
    collection_name = settings.QDRANT_COLLECTION_NAME
    vector_dimension = settings.QDRANT_VECTOR_DIMENSION

    ensure_collection(client, collection_name, vector_dimension)

    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    meetings_by_id = {meeting.get("meeting_id"): meeting for meeting in meetings}

    points = []
    indexed_count = 0
    skipped_count = 0

    for item in items:
        meeting = meetings_by_id.get(item.get("meeting_id"), {})
        text = build_meeting_item_embedding_text(meeting, item)
        if not text:
            skipped_count += 1
            continue

        vector = embedder(text)
        validate_vector(vector, vector_dimension)
        points.append(make_point(item, meeting, text, vector))
        indexed_count += 1

        if len(points) >= batch_size:
            upsert_points(client, collection_name, points)
            points = []

    if points:
        upsert_points(client, collection_name, points)

    return {
        "collection_name": collection_name,
        "embedding_model": settings.OLLAMA_EMBEDDING_MODEL,
        "vector_dimension": vector_dimension,
        "indexed_count": indexed_count,
        "skipped_count": skipped_count,
    }


def semantic_search(query: str, limit: int = 10, client=None, embedder=None) -> dict:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise VectorServiceError("Query is required.")

    client = client or get_qdrant_client()
    embedder = embedder or ollama_embedding
    collection_name = settings.QDRANT_COLLECTION_NAME
    vector = embedder(normalized_query)
    validate_vector(vector, settings.QDRANT_VECTOR_DIMENSION)

    points = search_points(client, collection_name, vector, limit=limit)
    return {
        "query": normalized_query,
        "collection_name": collection_name,
        "results": [serialize_scored_point(point) for point in points],
    }


def build_meeting_item_embedding_text(meeting: dict, item: dict) -> str:
    parts = [
        ("meeting_name", meeting.get("meeting_name")),
        ("meeting_date", meeting.get("meeting_date")),
        ("responsible_unit", semantic_text_value(meeting.get("responsible_unit"))),
        ("item_no", item.get("item_no")),
        ("content", semantic_text_value(item.get("content"))),
        ("owner", semantic_text_value(item.get("owner"))),
        ("planned_date", item.get("planned_date")),
        ("actual_completed_date", item.get("actual_completed_date")),
        ("tracking_result", semantic_text_value(item.get("tracking_result"))),
        ("status", item_status_payload(item)["status"]),
    ]
    lines = [f"{field}: {value}" for field, value in parts if has_text(value)]
    return "\n".join(lines)


def make_point(item: dict, meeting: dict, text: str, vector: list[float]):
    point_id = str(uuid5(NAMESPACE_URL, str(item.get("item_id"))))
    payload = {
        "document_id": item.get("document_id") or meeting.get("document_id"),
        "meeting_id": item.get("meeting_id"),
        "item_id": item.get("item_id"),
        "item_no": item.get("item_no"),
        "meeting_name": meeting.get("meeting_name"),
        "meeting_date": meeting.get("meeting_date"),
        "content": item.get("content"),
        "owner": item.get("owner"),
        "planned_date": item.get("planned_date"),
        "actual_completed_date": item.get("actual_completed_date"),
        "tracking_result": item.get("tracking_result"),
        "status": item_status_payload(item)["status"],
        "status_source": item_status_payload(item)["source"],
        "status_confidence": item_status_payload(item)["confidence"],
        "embedding_text": text,
    }

    models = get_qdrant_models(required=False)
    if models and hasattr(models, "PointStruct"):
        return models.PointStruct(id=point_id, vector=vector, payload=payload)
    return {"id": point_id, "vector": vector, "payload": payload}


def get_qdrant_client():
    try:
        from qdrant_client import QdrantClient
    except Exception as exc:
        raise VectorServiceError("qdrant-client is not installed.") from exc

    try:
        return QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    except Exception as exc:
        raise VectorServiceError(f"Unable to initialize Qdrant client: {exc}") from exc


def get_qdrant_models(required=True):
    try:
        from qdrant_client import models

        return models
    except Exception as exc:
        if required:
            raise VectorServiceError("qdrant-client is not installed.") from exc
        return None


def ensure_collection(client, collection_name: str, vector_dimension: int) -> None:
    try:
        client.get_collection(collection_name)
        return
    except Exception:
        pass

    try:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=make_vectors_config(vector_dimension),
        )
    except Exception as exc:
        raise VectorServiceError(f"Unable to create Qdrant collection '{collection_name}': {exc}") from exc


def make_vectors_config(vector_dimension: int):
    models = get_qdrant_models(required=False)
    if models and hasattr(models, "VectorParams"):
        return models.VectorParams(size=vector_dimension, distance=models.Distance.COSINE)
    return {"size": vector_dimension, "distance": "Cosine"}


def upsert_points(client, collection_name: str, points: list) -> None:
    try:
        client.upsert(collection_name=collection_name, points=points)
    except Exception as exc:
        raise VectorServiceError(f"Unable to upsert vectors into '{collection_name}': {exc}") from exc


def search_points(client, collection_name: str, vector: list[float], limit: int):
    try:
        if hasattr(client, "query_points"):
            result = client.query_points(collection_name=collection_name, query=vector, limit=limit)
            return getattr(result, "points", result)
        return client.search(collection_name=collection_name, query_vector=vector, limit=limit)
    except Exception as exc:
        raise VectorServiceError(f"Unable to search Qdrant collection '{collection_name}': {exc}") from exc


def ollama_embedding(text: str) -> list[float]:
    try:
        import requests
    except Exception as exc:
        raise VectorServiceError("requests is not installed.") from exc

    url = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}/api/embeddings"
    try:
        response = requests.post(
            url,
            json={"model": settings.OLLAMA_EMBEDDING_MODEL, "prompt": text},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise VectorServiceError(f"Unable to generate Ollama embedding: {exc}") from exc

    vector = payload.get("embedding")
    if not isinstance(vector, list):
        raise VectorServiceError("Ollama embedding response did not include an embedding vector.")
    return vector


def validate_vector(vector: list[float], expected_dimension: int) -> None:
    if not isinstance(vector, list) or not vector:
        raise VectorServiceError("Embedding vector is empty or invalid.")
    if len(vector) != expected_dimension:
        raise VectorServiceError(
            f"Embedding dimension mismatch: expected {expected_dimension}, got {len(vector)}."
        )


def serialize_scored_point(point) -> dict:
    payload = dict(getattr(point, "payload", None) or point.get("payload", {}))
    score = getattr(point, "score", None)
    if score is None and isinstance(point, dict):
        score = point.get("score")
    payload["semantic_score"] = float(score or 0)
    return payload


def has_text(value) -> bool:
    return is_meaningful_value(value)


def semantic_text_value(value):
    if not isinstance(value, str):
        return value
    if PSEUDONYM_TOKEN_PATTERN.fullmatch(value.strip()):
        return None
    return PSEUDONYM_TOKEN_PATTERN.sub(lambda match: neutral_text_placeholder(match.group(1)), value)


def neutral_text_placeholder(kind: str) -> str:
    return {
        "Person": "人員",
        "Unit": "單位",
        "Company": "公司",
        "File": "文件",
        "Ref": "編號",
        "Email": "電子郵件",
        "Phone": "電話",
        "ID": "身分識別碼",
        "Token": "識別碼",
    }.get(kind, "識別碼")
