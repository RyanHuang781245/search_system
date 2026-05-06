from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from uuid import uuid4
import mimetypes

from bson import ObjectId
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from pymongo import ReturnDocument

from .mongo import get_documents_collection


def _generate_document_id():
    date_part = timezone.localtime().strftime("%Y%m%d")
    return f"doc_{date_part}_{uuid4().hex[:6]}"


def _normalize_tags(tags):
    if tags is None:
        return []
    if isinstance(tags, list):
        return [str(tag).strip() for tag in tags if str(tag).strip()]
    return [tag.strip() for tag in str(tags).split(",") if tag.strip()]


def _serialize_document(document):
    if not document:
        return None
    serialized = dict(document)
    if isinstance(serialized.get("_id"), ObjectId):
        serialized["_id"] = str(serialized["_id"])
    for field in ("created_at", "updated_at", "deleted_at", "file_modified_at"):
        value = serialized.get(field)
        if isinstance(value, datetime):
            if timezone.is_naive(value):
                value = timezone.make_aware(value, dt_timezone.utc)
            serialized[field] = timezone.localtime(value).isoformat()
    return serialized


def resolve_file_modified_at(file_modified_at=None, absolute_file_path=None):
    if file_modified_at:
        parsed = parse_datetime(str(file_modified_at))
        if parsed:
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed

    if absolute_file_path:
        path = Path(absolute_file_path)
        if path.exists():
            timestamp = path.stat().st_mtime
            return datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())

    return timezone.now()


def save_uploaded_file(file_obj):
    document_id = _generate_document_id()
    extension = Path(file_obj.name).suffix.lower()
    stored_filename = f"{document_id}{extension}"
    destination = settings.UPLOAD_ROOT / stored_filename

    with destination.open("wb+") as output:
        for chunk in file_obj.chunks():
            output.write(chunk)

    return {
        "document_id": document_id,
        "stored_filename": stored_filename,
        "file_path": str(Path("uploads") / stored_filename).replace("\\", "/"),
        "absolute_file_path": str(destination),
        "file_ext": extension,
        "mime_type": file_obj.content_type or mimetypes.guess_type(stored_filename)[0] or "application/octet-stream",
        "file_size": file_obj.size,
    }


def create_document_record(
    file_obj,
    doc_type=None,
    description="",
    tags=None,
    saved_file=None,
    file_modified_at=None,
):
    collection = get_documents_collection()
    saved_file = saved_file or save_uploaded_file(file_obj)
    now = timezone.now()
    resolved_file_modified_at = resolve_file_modified_at(
        file_modified_at=file_modified_at,
        absolute_file_path=saved_file.get("absolute_file_path"),
    )

    document = {
        "document_id": saved_file["document_id"],
        "original_filename": file_obj.name,
        "stored_filename": saved_file["stored_filename"],
        "file_path": saved_file["file_path"],
        "file_ext": saved_file["file_ext"],
        "file_size": saved_file["file_size"],
        "mime_type": saved_file["mime_type"],
        "doc_type": doc_type or "unknown",
        "status": "uploaded",
        "page_count": None,
        "description": description or "",
        "tags": _normalize_tags(tags),
        "file_modified_at": resolved_file_modified_at,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "is_deleted": False,
    }

    collection.insert_one(document)
    return _serialize_document(document)


def list_documents(keyword=None, doc_type=None, status=None, page=1, limit=10):
    collection = get_documents_collection()
    query = {"is_deleted": False}

    if keyword:
        query["original_filename"] = {"$regex": keyword, "$options": "i"}
    if doc_type:
        query["doc_type"] = doc_type
    if status:
        query["status"] = status

    skip = max(page - 1, 0) * limit
    projection = {
        "_id": 0,
        "document_id": 1,
        "original_filename": 1,
        "doc_type": 1,
        "status": 1,
        "file_size": 1,
        "file_modified_at": 1,
        "created_at": 1,
    }

    total = collection.count_documents(query)
    documents = list(
        collection.find(query, projection).sort("created_at", -1).skip(skip).limit(limit)
    )
    return {
        "total": total,
        "documents": [_serialize_document(document) for document in documents],
    }


def get_document_detail(document_id):
    collection = get_documents_collection()
    document = collection.find_one(
        {"document_id": document_id, "is_deleted": False},
        {"_id": 0},
    )
    return _serialize_document(document)


def soft_delete_document(document_id):
    collection = get_documents_collection()
    now = timezone.now()
    updated = collection.find_one_and_update(
        {"document_id": document_id, "is_deleted": False},
        {
            "$set": {
                "is_deleted": True,
                "status": "deleted",
                "deleted_at": now,
                "updated_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0},
    )
    return _serialize_document(updated)
