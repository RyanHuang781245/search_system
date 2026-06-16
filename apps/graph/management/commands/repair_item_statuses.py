from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.graph.neo4j_client import get_neo4j_client
from apps.item_status import classify_item_status, is_meaningful_value
from apps.search.mongo import get_meeting_items_collection


class Command(BaseCommand):
    help = "Normalize placeholder item dates in Mongo and repair Neo4j item status/date relations."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without writing.")
        parser.add_argument("--limit", type=int, default=0, help="Limit processed items. 0 means all.")

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        limit = max(int(options.get("limit") or 0), 0)
        collection = get_meeting_items_collection()
        cursor = collection.find({}, {"_id": 0})
        if limit:
            cursor = cursor.limit(limit)
        items = list(cursor)

        mongo_updates = []
        status_payloads = []
        for item in items:
            updates = {}
            for field in ("planned_date", "actual_completed_date"):
                value = item.get(field)
                if value is not None and not is_meaningful_value(value):
                    updates[field] = None
            if updates:
                mongo_updates.append({"item_id": item.get("item_id"), "set": updates})
                if not dry_run:
                    collection.update_one({"item_id": item.get("item_id")}, {"$set": updates})
                    item.update(updates)
            status_payloads.append(build_status_payload(item))

        neo4j_summary = repair_neo4j_statuses(status_payloads, dry_run=dry_run)
        summary = {
            "dry_run": dry_run,
            "items_seen": len(items),
            "mongo_updates": len(mongo_updates),
            "mongo_update_preview": mongo_updates[:10],
            "neo4j": neo4j_summary,
        }
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


def build_status_payload(item: dict) -> dict:
    status = classify_item_status(item)
    return {
        "item_id": item.get("item_id"),
        "planned_date": item.get("planned_date") if is_meaningful_value(item.get("planned_date")) else None,
        "actual_completed_date": item.get("actual_completed_date") if is_meaningful_value(item.get("actual_completed_date")) else None,
        "status": status["status"],
        "status_source": status["source"],
        "status_confidence": status["confidence"],
    }


def repair_neo4j_statuses(status_payloads: list[dict], dry_run: bool = False) -> dict:
    client = get_neo4j_client()
    if not getattr(client, "available", False):
        return {"available": False, "items_seen": len(status_payloads), "items_written": 0}
    if dry_run:
        return {"available": True, "items_seen": len(status_payloads), "items_written": 0}

    def write(tx, payloads):
        if tx is None:
            return 0
        count = 0
        for payload in payloads:
            item_id = payload.get("item_id")
            if not item_id:
                continue
            tx.run(
                """
MATCH (item:MeetingItem {item_id: $item_id})
SET item.planned_date = $planned_date,
    item.actual_completed_date = $actual_completed_date
WITH item
OPTIONAL MATCH (item)-[planned:HAS_PLANNED_DATE]->(:Date)
DELETE planned
WITH item
OPTIONAL MATCH (item)-[completed:HAS_COMPLETED_DATE]->(:Date)
DELETE completed
WITH item
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
SET action.status = $status,
    action.status_source = $status_source,
    action.status_confidence = $status_confidence,
    action.planned_date = $planned_date,
    action.actual_completed_date = $actual_completed_date
""",
                **payload,
            )
            if payload.get("planned_date"):
                tx.run(
                    """
MATCH (item:MeetingItem {item_id: $item_id})
MERGE (date:Date {date_value: $planned_date, date_type: 'planned'})
MERGE (item)-[:HAS_PLANNED_DATE]->(date)
""",
                    **payload,
                )
            if payload.get("actual_completed_date"):
                tx.run(
                    """
MATCH (item:MeetingItem {item_id: $item_id})
MERGE (date:Date {date_value: $actual_completed_date, date_type: 'completed'})
MERGE (item)-[:HAS_COMPLETED_DATE]->(date)
""",
                    **payload,
                )
            count += 1
        return count

    written = client.execute_write(write, status_payloads)
    return {"available": True, "items_seen": len(status_payloads), "items_written": written}
