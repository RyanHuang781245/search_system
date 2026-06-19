from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from bson import ObjectId
from django.conf import settings
from django.utils import timezone

from apps.documents.mongo import get_documents_collection
from apps.documents.services import _serialize_document
from apps.item_status import apply_item_status_fields
from apps.parser.meeting_minutes_parser import parse_meeting_minutes
from apps.parser.pdf_text_extractor import PDFTextExtractor

from .mongo import get_meeting_items_collection, get_meeting_minutes_collection


def _serialize_mongo_document(document):
    if not document:
        return None
    serialized = dict(document)
    if isinstance(serialized.get("_id"), ObjectId):
        serialized["_id"] = str(serialized["_id"])
    for key in ("created_at", "updated_at"):
        value = serialized.get(key)
        if isinstance(value, datetime):
            if timezone.is_naive(value):
                value = timezone.make_aware(value, dt_timezone.utc)
            serialized[key] = timezone.localtime(value).isoformat()
    return serialized


def _resolve_document(document_id):
    collection = get_documents_collection()
    return collection.find_one({"document_id": document_id, "is_deleted": False}, {"_id": 0})


def parse_document_meeting_minutes(document_id):
    document = _resolve_document(document_id)
    if not document:
        return None
    if document.get("file_ext", "").lower() != ".pdf":
        raise ValueError("Only PDF meeting minutes can be parsed.")

    absolute_path = settings.UPLOAD_ROOT / document["stored_filename"]
    if not Path(absolute_path).exists():
        absolute_path = settings.BASE_DIR / document["file_path"]
    if not Path(absolute_path).exists():
        raise FileNotFoundError(str(absolute_path))

    payload = PDFTextExtractor(absolute_path).extract()
    parsed = parse_meeting_minutes(payload, document_id=document_id)

    documents_collection = get_documents_collection()
    minutes_collection = get_meeting_minutes_collection()
    items_collection = get_meeting_items_collection()
    now = timezone.now()

    update_fields = {
        "page_count": payload["page_count"],
        "updated_at": now,
    }

    if parsed["status"] == "needs_ocr":
        update_fields["status"] = "needs_ocr"
        documents_collection.update_one({"document_id": document_id}, {"$set": update_fields})
        return {
            "document": _serialize_document(documents_collection.find_one({"document_id": document_id}, {"_id": 0})),
            "meeting_minutes": None,
            "meeting_items": [],
            "status": "needs_ocr",
        }

    minutes_collection.delete_many({"document_id": document_id})
    items_collection.delete_many({"document_id": document_id})

    meeting_minutes = dict(parsed["meeting_minutes"])
    meeting_minutes.update(
        {
            "created_at": now,
            "updated_at": now,
        }
    )
    minutes_collection.insert_one(meeting_minutes)

    meeting_items = []
    for item in parsed["meeting_items"]:
        row = apply_item_status_fields(item)
        row.update({"created_at": now, "updated_at": now})
        meeting_items.append(row)

    if meeting_items:
        items_collection.insert_many(meeting_items)

    update_fields["status"] = "parsed"
    documents_collection.update_one({"document_id": document_id}, {"$set": update_fields})

    return {
        "document": _serialize_document(documents_collection.find_one({"document_id": document_id}, {"_id": 0})),
        "meeting_minutes": _serialize_mongo_document(meeting_minutes),
        "meeting_items": [_serialize_mongo_document(item) for item in meeting_items],
        "status": "parsed",
    }


def list_meeting_minutes(keyword=None, meeting_name=None, date_from=None, date_to=None, responsible_unit=None):
    collection = get_meeting_minutes_collection()
    query = {}
    if keyword:
        query["$or"] = [
            {"meeting_name": {"$regex": keyword, "$options": "i"}},
            {"raw_text": {"$regex": keyword, "$options": "i"}},
            {"attendees": {"$elemMatch": {"$regex": keyword, "$options": "i"}}},
        ]
    if meeting_name:
        query["meeting_name"] = {"$regex": meeting_name, "$options": "i"}
    if responsible_unit:
        query["responsible_unit"] = responsible_unit
    if date_from or date_to:
        date_query = {}
        if date_from:
            date_query["$gte"] = date_from
        if date_to:
            date_query["$lte"] = date_to
        query["meeting_date"] = date_query

    projection = {"_id": 0}
    meetings = list(collection.find(query, projection).sort("meeting_date", -1).sort("created_at", -1))
    return {"total": len(meetings), "meeting_minutes": [_serialize_mongo_document(item) for item in meetings]}


def get_meeting_minutes_detail(meeting_id):
    minutes_collection = get_meeting_minutes_collection()
    items_collection = get_meeting_items_collection()

    meeting = minutes_collection.find_one({"meeting_id": meeting_id}, {"_id": 0})
    if not meeting:
        return None

    items = list(items_collection.find({"meeting_id": meeting_id}, {"_id": 0}).sort("page_number", 1))
    items.sort(key=lambda item: (item.get("page_number", 0), item.get("item_no", "")))

    return {
        "meeting_minutes": _serialize_mongo_document(meeting),
        "meeting_items": [_serialize_mongo_document(item) for item in items],
    }


def list_meeting_items(keyword=None, owner=None, planned_date=None, meeting_id=None):
    collection = get_meeting_items_collection()
    query = {}
    if keyword:
        query["$or"] = [
            {"content": {"$regex": keyword, "$options": "i"}},
            {"tracking_result": {"$regex": keyword, "$options": "i"}},
            {"raw_row_text": {"$regex": keyword, "$options": "i"}},
        ]
    if owner:
        query["owner"] = {"$regex": owner, "$options": "i"}
    if planned_date:
        query["planned_date"] = planned_date
    if meeting_id:
        query["meeting_id"] = meeting_id

    items = list(collection.find(query, {"_id": 0}).sort("planned_date", 1))
    items.sort(key=lambda item: (item.get("meeting_id", ""), item.get("page_number", 0), item.get("item_no", "")))
    return {"total": len(items), "meeting_items": [_serialize_mongo_document(item) for item in items]}
