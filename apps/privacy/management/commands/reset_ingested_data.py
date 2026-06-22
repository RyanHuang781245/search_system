from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.documents.mongo import get_database
from apps.graph.management.commands.deidentify_data import NEO4J_NODE_LABELS
from apps.graph.neo4j_client import get_neo4j_client
from apps.vector.services import get_qdrant_client


MONGO_COLLECTIONS = (
    "documents",
    "meeting_minutes",
    "meeting_items",
    "search_logs",
    "search_click_logs",
)


class Command(BaseCommand):
    help = "Clear ingested MongoDB, Neo4j, and Qdrant data before re-importing with pre-write de-identification."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually delete data. Default is dry-run.")
        parser.add_argument("--skip-mongo", action="store_true")
        parser.add_argument("--skip-neo4j", action="store_true")
        parser.add_argument("--skip-qdrant", action="store_true")
        parser.add_argument("--delete-uploads", action="store_true", help="Also delete files under UPLOAD_ROOT.")

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        summary = {
            "dry_run": not apply_changes,
            "mongo": {"skipped": bool(options["skip_mongo"])},
            "neo4j": {"skipped": bool(options["skip_neo4j"])},
            "qdrant": {"skipped": bool(options["skip_qdrant"])},
            "uploads": {"skipped": not bool(options["delete_uploads"])},
        }
        if not options["skip_mongo"]:
            summary["mongo"] = reset_mongo(apply_changes)
        if not options["skip_neo4j"]:
            summary["neo4j"] = reset_neo4j(apply_changes)
        if not options["skip_qdrant"]:
            summary["qdrant"] = reset_qdrant(apply_changes)
        if options["delete_uploads"]:
            summary["uploads"] = reset_uploads(apply_changes)
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def reset_mongo(apply_changes: bool) -> dict:
    db = get_database()
    collections = {}
    for name in MONGO_COLLECTIONS:
        count = db[name].count_documents({})
        if apply_changes:
            db[name].delete_many({})
        collections[name] = {"records": count, "deleted": apply_changes}
    return {"collections": collections}


def reset_neo4j(apply_changes: bool) -> dict:
    client = get_neo4j_client()
    if not getattr(client, "available", False):
        return {"available": False, "deleted": False}

    def count_nodes(tx):
        row = tx.run(
            """
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN $labels)
RETURN count(n) AS count
""",
            labels=list(NEO4J_NODE_LABELS),
        ).single()
        return int(row["count"] or 0) if row else 0

    def delete_nodes(tx):
        row = tx.run(
            """
MATCH (n)
WHERE any(label IN labels(n) WHERE label IN $labels)
WITH collect(n) AS nodes, count(n) AS count
FOREACH (node IN nodes | DETACH DELETE node)
RETURN count
""",
            labels=list(NEO4J_NODE_LABELS),
        ).single()
        return int(row["count"] or 0) if row else 0

    count = client.execute_read(count_nodes)
    deleted = client.execute_write(delete_nodes) if apply_changes else 0
    return {"available": True, "nodes": count, "deleted_nodes": deleted, "deleted": apply_changes}


def reset_qdrant(apply_changes: bool) -> dict:
    try:
        client = get_qdrant_client()
        collection_name = settings.QDRANT_COLLECTION_NAME
        try:
            collection = client.get_collection(collection_name=collection_name)
            point_count = getattr(collection, "points_count", None)
        except Exception:
            point_count = None
        if apply_changes:
            try:
                client.delete_collection(collection_name=collection_name)
                deleted = True
            except Exception:
                deleted = False
        else:
            deleted = False
        return {
            "available": True,
            "collection_name": collection_name,
            "points": point_count,
            "deleted": deleted,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc), "deleted": False}


def reset_uploads(apply_changes: bool) -> dict:
    root = Path(settings.UPLOAD_ROOT).resolve()
    base = Path(settings.BASE_DIR).resolve()
    if not root.is_relative_to(base):
        return {"root": str(root), "error": "UPLOAD_ROOT is outside BASE_DIR.", "deleted": False}

    files = [path for path in root.rglob("*") if path.is_file()]
    if apply_changes:
        for path in files:
            path.unlink()
        for path in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
            if path != root:
                try:
                    path.rmdir()
                except OSError:
                    pass
    return {"root": str(root), "files": len(files), "deleted": apply_changes}
