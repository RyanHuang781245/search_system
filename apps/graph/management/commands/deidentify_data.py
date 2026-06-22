from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from bson import ObjectId
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.documents.mongo import get_database
from apps.graph.graph_builder import build_graph_from_mongo
from apps.graph.neo4j_client import get_neo4j_client
from apps.vector.services import get_qdrant_client, index_meeting_items


MISSING_VALUES = {"", "-", "--", "na", "n/a", "none", "null"}
ID_KEYS = {
    "_id",
    "document_id",
    "meeting_id",
    "item_id",
    "search_id",
    "click_id",
    "action_id",
    "decision_id",
    "risk_id",
    "issue_id",
}
PASSTHROUGH_KEYS = ID_KEYS | {
    "stored_filename",
    "file_path",
    "absolute_file_path",
    "file_ext",
    "mime_type",
    "doc_type",
    "status",
    "status_source",
    "status_confidence",
    "meeting_date",
    "start_time",
    "end_time",
    "planned_date",
    "actual_completed_date",
    "created_at",
    "updated_at",
    "deleted_at",
    "file_modified_at",
    "page_count",
    "file_size",
    "is_deleted",
    "result_count",
}
PERSON_KEYS = {"chairperson", "recorder", "owner", "person", "person_name", "matched_entity"}
UNIT_KEYS = {"responsible_unit", "unit", "unit_name"}
COMPANY_KEYS = {"company_name"}
LOCATION_KEYS = {"location"}
FILE_KEYS = {"original_filename"}
REF_KEYS = {"form_no", "ref_no"}
TEXT_KEYS = {
    "meeting_name",
    "content",
    "tracking_result",
    "raw_row_text",
    "raw_text",
    "description",
    "query",
    "embedding_text",
    "title",
    "evidence",
    "signature",
    "name",
}
RETRIEVAL_TEXT_FIELDS = {
    "meeting_minutes": ("raw_text",),
    "meeting_items": ("content", "tracking_result", "raw_row_text"),
    "search_logs": ("query", "filters"),
    "search_click_logs": ("query",),
}
MONGO_COLLECTIONS = (
    "documents",
    "meeting_minutes",
    "meeting_items",
    "search_logs",
    "search_click_logs",
)
NEO4J_NODE_LABELS = (
    "Document",
    "Meeting",
    "MeetingItem",
    "Person",
    "Unit",
    "Keyword",
    "ActionItem",
    "Decision",
    "Risk",
    "Issue",
)


class Command(BaseCommand):
    help = "De-identify MongoDB, Neo4j, and Qdrant data. Defaults to dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Write anonymized values. Default is dry-run.")
        parser.add_argument("--salt", default="", help="Salt used for deterministic pseudonyms.")
        parser.add_argument(
            "--salt-env",
            default="DEIDENTIFICATION_SALT",
            help="Environment variable containing the salt when --salt is omitted.",
        )
        parser.add_argument("--limit", type=int, default=0, help="Limit records per store for testing. 0 means all.")
        parser.add_argument("--skip-mongo", action="store_true", help="Do not process MongoDB.")
        parser.add_argument("--skip-neo4j", action="store_true", help="Do not process Neo4j.")
        parser.add_argument("--skip-qdrant", action="store_true", help="Do not process Qdrant.")
        parser.add_argument(
            "--rebuild-neo4j",
            action="store_true",
            help="After MongoDB is written, clear and rebuild the Neo4j graph from anonymized MongoDB data.",
        )
        parser.add_argument(
            "--rebuild-qdrant",
            action="store_true",
            help="After MongoDB is written, delete and rebuild the Qdrant collection with anonymized text.",
        )
        parser.add_argument("--qdrant-batch-size", type=int, default=64)
        parser.add_argument(
            "--clear-search-history",
            action="store_true",
            help="Delete search_logs and search_click_logs after de-identification to remove stale feedback ranking.",
        )
        parser.add_argument(
            "--neutralize-pseudonyms-in-text",
            action="store_true",
            help="Replace existing Person_/Unit_ tokens in long text with neutral labels before rebuilding retrievers.",
        )
        parser.add_argument(
            "--mapping-file",
            default="",
            help="Optional sensitive JSON file containing original-to-anonymized mappings.",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        skip_mongo = bool(options["skip_mongo"])
        skip_neo4j = bool(options["skip_neo4j"])
        skip_qdrant = bool(options["skip_qdrant"])
        uses_pseudonymizer_for_writes = (
            not skip_mongo
            or (not skip_neo4j and not options["rebuild_neo4j"])
            or (not skip_qdrant and not options["rebuild_qdrant"])
        )
        salt = str(options["salt"] or os.getenv(options["salt_env"], "")).strip()
        if apply_changes and uses_pseudonymizer_for_writes and not salt:
            raise CommandError("Provide --salt or set the configured salt environment variable before --apply.")
        if not salt:
            salt = "dry-run"

        limit = max(int(options["limit"] or 0), 0)

        mongo_values = collect_mongo_sensitive_values(limit=limit) if not skip_mongo else defaultdict(set)
        neo4j_values = collect_neo4j_sensitive_values() if not skip_neo4j else defaultdict(set)
        pseudonymizer = Pseudonymizer(salt=salt, values=merge_values(mongo_values, neo4j_values))

        summary = {
            "dry_run": not apply_changes,
            "mongo": {"skipped": skip_mongo},
            "neo4j": {"skipped": skip_neo4j},
            "qdrant": {"skipped": skip_qdrant},
            "neo4j_rebuild_requested": bool(options["rebuild_neo4j"]),
            "qdrant_rebuild_requested": bool(options["rebuild_qdrant"]),
            "clear_search_history_requested": bool(options["clear_search_history"]),
            "neutralize_pseudonyms_in_text_requested": bool(options["neutralize_pseudonyms_in_text"]),
        }

        if not skip_mongo:
            summary["mongo"] = deidentify_mongo(pseudonymizer, apply_changes=apply_changes, limit=limit)
        if options["neutralize_pseudonyms_in_text"]:
            summary["retrieval_text"] = neutralize_pseudonyms_in_mongo_text(apply_changes=apply_changes, limit=limit)
        if not skip_neo4j:
            if options["rebuild_neo4j"]:
                summary["neo4j"] = rebuild_neo4j(apply_changes=apply_changes)
            else:
                summary["neo4j"] = deidentify_neo4j(pseudonymizer, apply_changes=apply_changes, limit=limit)
        if not skip_qdrant:
            summary["qdrant"] = deidentify_qdrant(
                pseudonymizer,
                apply_changes=apply_changes,
                limit=limit,
                rebuild=bool(options["rebuild_qdrant"]),
                batch_size=max(int(options["qdrant_batch_size"] or 64), 1),
            )
        if options["clear_search_history"]:
            summary["search_history"] = clear_search_history(apply_changes=apply_changes)

        mapping_file = str(options["mapping_file"] or "").strip()
        if mapping_file:
            mapping_summary = write_mapping_file(
                mapping_file,
                pseudonymizer,
                dry_run=not apply_changes,
            )
            summary["mapping_file"] = mapping_summary

        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


class Pseudonymizer:
    def __init__(self, salt: str, values: dict[str, set[str]]):
        self.salt = salt
        self.values = values
        self.mapping = {}
        self.replacements = []
        for kind, originals in values.items():
            for original in originals:
                replacement = self.value(kind, original)
                self.replacements.append((original, kind, replacement))
        self.replacements.sort(key=lambda item: len(item[0]), reverse=True)

    def value(self, kind: str, value):
        text = normalize_value(value)
        if not text:
            return value
        digest = hashlib.sha256(f"{self.salt}\0{kind}\0{text}".encode("utf-8")).hexdigest()[:10].upper()
        prefixes = {
            "person": "Person",
            "unit": "Unit",
            "company": "Company",
            "location": "Location",
            "file": "File",
            "ref": "Ref",
        }
        replacement = f"{prefixes.get(kind, 'Token')}_{digest}"
        self._remember(kind, text, replacement)
        return replacement

    def filename(self, value):
        text = normalize_value(value)
        if not text:
            return value
        suffix = Path(text).suffix
        replacement = f"{self.value('file', text)}{suffix}"
        self._remember("file", text, replacement)
        return replacement

    def token(self, kind: str, value, prefix: str):
        text = normalize_value(value)
        if not text:
            return value
        digest = hashlib.sha256(f"{self.salt}\0{kind}\0{text}".encode("utf-8")).hexdigest()[:10].upper()
        replacement = f"{prefix}_{digest}"
        self._remember(kind, text, replacement)
        return replacement

    def text(self, value):
        if not isinstance(value, str):
            return value
        result = value
        for original, kind, _replacement in self.replacements:
            result = result.replace(original, neutral_text_placeholder(kind))
        result = replace_regex_tokens(result, self, EMAIL_PATTERN, "Email")
        result = replace_regex_tokens(result, self, TAIWAN_ID_PATTERN, "ID")
        result = replace_regex_tokens(result, self, PHONE_PATTERN, "Phone")
        result = neutralize_pseudonym_tokens(result)
        return result

    def records(self) -> list[dict]:
        rows = [
            {"kind": kind, "original": original, "anonymized": anonymized}
            for (kind, original), anonymized in self.mapping.items()
        ]
        rows.sort(key=lambda row: (row["kind"], row["original"]))
        return rows

    def _remember(self, kind: str, original: str, anonymized: str) -> None:
        if original and anonymized and original != anonymized:
            self.mapping[(kind, original)] = anonymized


EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
TAIWAN_ID_PATTERN = re.compile(r"\b[A-Z][12]\d{8}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
PSEUDONYM_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(Person|Unit|Company|File|Ref|Email|Phone|ID|Token)_[A-F0-9]{10}(?![A-Za-z0-9_])")


def replace_regex_tokens(text: str, pseudonymizer: Pseudonymizer, pattern: re.Pattern, prefix: str) -> str:
    def repl(match):
        if prefix == "Phone" and sum(char.isdigit() for char in match.group(0)) < 9:
            return match.group(0)
        pseudonymizer.token(prefix.lower(), match.group(0), prefix)
        return neutral_text_placeholder(prefix.lower())

    return pattern.sub(repl, text)


def neutral_text_placeholder(kind: str) -> str:
    return {
        "person": "人員",
        "unit": "單位",
        "company": "公司",
        "location": "地點",
        "file": "文件",
        "ref": "編號",
        "email": "電子郵件",
        "phone": "電話",
        "id": "身分識別碼",
        "token": "識別碼",
    }.get(str(kind or "").lower(), "識別碼")


def neutralize_pseudonym_tokens(text: str) -> str:
    def repl(match):
        return neutral_text_placeholder(match.group(1).lower())

    return PSEUDONYM_TOKEN_PATTERN.sub(repl, text)


def write_mapping_file(path: str, pseudonymizer: Pseudonymizer, dry_run: bool) -> dict:
    destination = Path(path)
    if destination.parent != Path("."):
        destination.parent.mkdir(parents=True, exist_ok=True)
    records = pseudonymizer.records()
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "warning": "This file contains original sensitive values. Keep it separate from the de-identified database.",
        "record_count": len(records),
        "records": records,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(destination), "record_count": len(records)}


def normalize_value(value) -> str:
    text = str(value or "").strip()
    if text.lower() in MISSING_VALUES:
        return ""
    return text


def merge_values(*sources: dict[str, set[str]]) -> dict[str, set[str]]:
    merged = defaultdict(set)
    for source in sources:
        for key, values in source.items():
            merged[key].update(normalize_value(value) for value in values if normalize_value(value))
    return merged


def collect_mongo_sensitive_values(limit: int = 0) -> dict[str, set[str]]:
    db = get_database()
    values = defaultdict(set)
    for collection_name in MONGO_COLLECTIONS:
        collection = db[collection_name]
        cursor = collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        for document in cursor:
            collect_values_from_document(document, values)
    return values


def collect_values_from_document(value, values: dict[str, set[str]], key: str = "") -> None:
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            collect_values_from_document(child_value, values, child_key)
        return
    if isinstance(value, list):
        for item in value:
            collect_values_from_document(item, values, key)
        return

    text = normalize_value(value)
    if not text:
        return
    if key in PERSON_KEYS or key == "attendees":
        values["person"].add(text)
    elif key in UNIT_KEYS:
        values["unit"].add(text)
    elif key in COMPANY_KEYS:
        values["company"].add(text)
    elif key in LOCATION_KEYS:
        values["location"].add(text)
    elif key in FILE_KEYS:
        values["file"].add(text)
    elif key in REF_KEYS:
        values["ref"].add(text)


def collect_neo4j_sensitive_values() -> dict[str, set[str]]:
    values = defaultdict(set)
    client = get_neo4j_client()
    if not getattr(client, "available", False):
        return values

    def read(tx):
        if tx is None:
            return []
        return [dict(row) for row in tx.run(
            """
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN $labels)
RETURN labels(n) AS labels, properties(n) AS props
""",
            labels=list(NEO4J_NODE_LABELS),
        )]

    for row in client.execute_read(read):
        labels = set(row.get("labels") or [])
        props = row.get("props") or {}
        if "Person" in labels:
            add_value(values, "person", props.get("name"))
        if "Unit" in labels:
            add_value(values, "unit", props.get("name"))
        if "Document" in labels:
            add_value(values, "file", props.get("original_filename"))
        add_value(values, "unit", props.get("responsible_unit"))
    return values


def add_value(values: dict[str, set[str]], kind: str, value) -> None:
    text = normalize_value(value)
    if text:
        values[kind].add(text)


def deidentify_mongo(pseudonymizer: Pseudonymizer, apply_changes: bool, limit: int = 0) -> dict:
    db = get_database()
    summary = {"collections": {}, "records_seen": 0, "records_changed": 0}
    for collection_name in MONGO_COLLECTIONS:
        collection = db[collection_name]
        cursor = collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        seen = 0
        changed = 0
        previews = []
        for document in cursor:
            seen += 1
            transformed = anonymize_document(document, pseudonymizer)
            updates = changed_top_level_fields(document, transformed)
            if not updates:
                continue
            changed += 1
            if len(previews) < 5:
                previews.append({"id": str(document.get("_id")), "fields": sorted(updates)})
            if apply_changes:
                collection.update_one({"_id": document["_id"]}, {"$set": updates})
        summary["collections"][collection_name] = {"seen": seen, "changed": changed, "preview": previews}
        summary["records_seen"] += seen
        summary["records_changed"] += changed
    return summary


def neutralize_pseudonyms_in_mongo_text(apply_changes: bool, limit: int = 0) -> dict:
    db = get_database()
    summary = {"dry_run": not apply_changes, "collections": {}, "records_seen": 0, "records_changed": 0}
    for collection_name, fields in RETRIEVAL_TEXT_FIELDS.items():
        collection = db[collection_name]
        cursor = collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        seen = 0
        changed = 0
        previews = []
        for document in cursor:
            seen += 1
            updates = {}
            for field in fields:
                old_value = document.get(field)
                new_value = neutralize_pseudonym_value(old_value)
                if old_value != new_value:
                    updates[field] = new_value
            if not updates:
                continue
            changed += 1
            if len(previews) < 5:
                previews.append({"id": str(document.get("_id")), "fields": sorted(updates)})
            if apply_changes:
                collection.update_one({"_id": document["_id"]}, {"$set": updates})
        summary["collections"][collection_name] = {"seen": seen, "changed": changed, "preview": previews}
        summary["records_seen"] += seen
        summary["records_changed"] += changed
    return summary


def neutralize_pseudonym_value(value):
    if isinstance(value, dict):
        return {key: neutralize_pseudonym_value(child_value) for key, child_value in value.items()}
    if isinstance(value, list):
        return [neutralize_pseudonym_value(item) for item in value]
    if isinstance(value, str):
        return neutralize_pseudonym_tokens(value)
    return value


def anonymize_document(document: dict, pseudonymizer: Pseudonymizer) -> dict:
    return {
        key: value if key == "_id" else anonymize_value(value, pseudonymizer, key)
        for key, value in document.items()
    }


def anonymize_value(value, pseudonymizer: Pseudonymizer, key: str = ""):
    if isinstance(value, dict):
        return {child_key: anonymize_value(child_value, pseudonymizer, child_key) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [anonymize_value(item, pseudonymizer, key) for item in value]
    if key in PASSTHROUGH_KEYS or isinstance(value, ObjectId):
        return value
    if key in PERSON_KEYS or key == "attendees":
        return pseudonymizer.value("person", value)
    if key in UNIT_KEYS:
        return pseudonymizer.value("unit", value)
    if key in COMPANY_KEYS:
        return pseudonymizer.value("company", value)
    if key in LOCATION_KEYS:
        return pseudonymizer.value("location", value)
    if key in FILE_KEYS:
        return pseudonymizer.filename(value)
    if key in REF_KEYS:
        return pseudonymizer.value("ref", value)
    if isinstance(value, str):
        return pseudonymizer.text(value)
    return value


def changed_top_level_fields(original: dict, transformed: dict) -> dict:
    updates = {}
    for key, new_value in transformed.items():
        if key == "_id":
            continue
        if original.get(key) != new_value:
            updates[key] = new_value
    return updates


def deidentify_neo4j(pseudonymizer: Pseudonymizer, apply_changes: bool, limit: int = 0) -> dict:
    client = get_neo4j_client()
    if not getattr(client, "available", False):
        return {"available": False, "nodes_seen": 0, "nodes_changed": 0}

    def read(tx):
        if tx is None:
            return []
        query = """
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN $labels)
RETURN elementId(n) AS element_id, labels(n) AS labels, properties(n) AS props
"""
        if limit:
            query += "\nLIMIT $limit"
        return [dict(row) for row in tx.run(query, labels=list(NEO4J_NODE_LABELS), limit=limit)]

    rows = client.execute_read(read)
    changed_payloads = []
    for row in rows:
        labels = set(row.get("labels") or [])
        props = row.get("props") or {}
        updates = anonymize_neo4j_properties(labels, props, pseudonymizer)
        updates = {key: value for key, value in updates.items() if props.get(key) != value}
        if updates:
            changed_payloads.append({"element_id": row["element_id"], "props": updates})

    if apply_changes and changed_payloads:
        def write(tx, payloads):
            if tx is None:
                return 0
            for payload in payloads:
                tx.run(
                    """
MATCH (n)
WHERE elementId(n) = $element_id
SET n += $props
""",
                    element_id=payload["element_id"],
                    props=payload["props"],
                )
            return len(payloads)

        client.execute_write(write, changed_payloads)

    return {
        "available": True,
        "nodes_seen": len(rows),
        "nodes_changed": len(changed_payloads),
        "preview": [{"element_id": item["element_id"], "fields": sorted(item["props"])} for item in changed_payloads[:5]],
    }


def rebuild_neo4j(apply_changes: bool) -> dict:
    client = get_neo4j_client()
    if not getattr(client, "available", False):
        return {"available": False, "rebuild": "unavailable"}
    if not apply_changes:
        return {"available": True, "rebuild": "dry-run"}

    def clear(tx):
        if tx is None:
            return 0
        result = tx.run(
            """
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN $labels)
WITH collect(n) AS nodes, count(n) AS count
FOREACH (node IN nodes | DETACH DELETE node)
RETURN count
""",
            labels=list(NEO4J_NODE_LABELS),
        )
        row = result.single()
        return int(row["count"] or 0) if row else 0

    deleted_nodes = client.execute_write(clear)
    build_summary = build_graph_from_mongo(client)
    return {
        "available": True,
        "rebuild": "completed",
        "deleted_nodes": deleted_nodes,
        **build_summary,
    }


def anonymize_neo4j_properties(labels: set[str], props: dict, pseudonymizer: Pseudonymizer) -> dict:
    updates = {}
    for key, value in props.items():
        if key in PASSTHROUGH_KEYS:
            continue
        if "Person" in labels and key == "name":
            updates[key] = pseudonymizer.value("person", value)
        elif "Unit" in labels and key == "name":
            updates[key] = pseudonymizer.value("unit", value)
        elif "Document" in labels and key == "original_filename":
            updates[key] = pseudonymizer.filename(value)
        else:
            updates[key] = anonymize_value(value, pseudonymizer, key)
    return updates


def deidentify_qdrant(
    pseudonymizer: Pseudonymizer,
    apply_changes: bool,
    limit: int = 0,
    rebuild: bool = False,
    batch_size: int = 64,
) -> dict:
    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME
        if rebuild:
            return rebuild_qdrant(client, collection_name, apply_changes=apply_changes, batch_size=batch_size)
        return scrub_qdrant_payloads(client, collection_name, pseudonymizer, apply_changes=apply_changes, limit=limit)
    except Exception as exc:
        return {"available": False, "error": str(exc), "points_seen": 0, "points_changed": 0}


def rebuild_qdrant(client, collection_name: str, apply_changes: bool, batch_size: int) -> dict:
    if not apply_changes:
        return {"available": True, "rebuild": "dry-run", "points_seen": 0, "points_changed": 0}
    try:
        client.delete_collection(collection_name=collection_name)
    except Exception:
        pass
    result = index_meeting_items(batch_size=batch_size, client=client)
    return {"available": True, "rebuild": "completed", **result}


def scrub_qdrant_payloads(client, collection_name: str, pseudonymizer: Pseudonymizer, apply_changes: bool, limit: int = 0) -> dict:
    offset = None
    seen = 0
    changed = 0
    previews = []
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=None,
            limit=64,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            if limit and seen >= limit:
                return {"available": True, "points_seen": seen, "points_changed": changed, "preview": previews}
            seen += 1
            payload = dict(getattr(point, "payload", {}) or {})
            new_payload = anonymize_value(payload, pseudonymizer)
            updates = changed_top_level_fields(payload, new_payload)
            if not updates:
                continue
            changed += 1
            point_id = getattr(point, "id", None)
            if len(previews) < 5:
                previews.append({"id": str(point_id), "fields": sorted(updates)})
            if apply_changes:
                client.set_payload(collection_name=collection_name, payload=updates, points=[point_id])
        if offset is None:
            break
    return {"available": True, "points_seen": seen, "points_changed": changed, "preview": previews}


def clear_search_history(apply_changes: bool) -> dict:
    db = get_database()
    logs_count = db["search_logs"].count_documents({})
    clicks_count = db["search_click_logs"].count_documents({})
    if apply_changes:
        db["search_logs"].delete_many({})
        db["search_click_logs"].delete_many({})
    return {
        "dry_run": not apply_changes,
        "search_logs": logs_count,
        "search_click_logs": clicks_count,
        "deleted": apply_changes,
    }
