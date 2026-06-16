from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand, CommandError

from apps.item_status import classify_item_status, is_meaningful_value
from apps.search.mongo import get_meeting_items_collection
from apps.graph.neo4j_client import get_neo4j_client


class Command(BaseCommand):
    help = "Inspect one or more meeting items across Mongo status rules and Neo4j ActionItem state."

    def add_arguments(self, parser):
        parser.add_argument("--item-id", dest="item_id", default="", help="Exact meeting item id.")
        parser.add_argument("--contains", dest="contains", default="", help="Text contained in content/tracking/raw row.")
        parser.add_argument("--limit", dest="limit", type=int, default=5)

    def handle(self, *args, **options):
        item_id = str(options.get("item_id") or "").strip()
        contains = str(options.get("contains") or "").strip()
        limit = max(int(options.get("limit") or 5), 1)
        if not item_id and not contains:
            raise CommandError("Provide --item-id or --contains.")

        items = find_mongo_items(item_id=item_id, contains=contains, limit=limit)
        if not items:
            self.stdout.write("No Mongo meeting_items matched.")
            return

        client = get_neo4j_client()
        for item in items:
            item_status = classify_item_status(item)
            neo4j_status = fetch_neo4j_status(client, item.get("item_id"))
            payload = {
                "item_id": item.get("item_id"),
                "meeting_id": item.get("meeting_id"),
                "item_no": item.get("item_no"),
                "content": item.get("content"),
                "owner": item.get("owner"),
                "planned_date": item.get("planned_date"),
                "actual_completed_date": item.get("actual_completed_date"),
                "tracking_result": item.get("tracking_result"),
                "raw_row_text": item.get("raw_row_text"),
                "mongo_rule_status": item_status,
                "mongo_value_flags": {
                    "planned_date_present": is_meaningful_value(item.get("planned_date")),
                    "actual_completed_date_present": is_meaningful_value(item.get("actual_completed_date")),
                    "tracking_result_present": is_meaningful_value(item.get("tracking_result")),
                },
                "neo4j": neo4j_status,
            }
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def find_mongo_items(item_id: str = "", contains: str = "", limit: int = 5) -> list[dict]:
    collection = get_meeting_items_collection()
    if item_id:
        query = {"item_id": item_id}
    else:
        pattern = loose_regex(contains)
        query = {
            "$or": [
                {"content": {"$regex": pattern, "$options": "i"}},
                {"tracking_result": {"$regex": pattern, "$options": "i"}},
                {"raw_row_text": {"$regex": pattern, "$options": "i"}},
            ]
        }
    return list(collection.find(query, {"_id": 0}).limit(limit))


def loose_regex(value: str) -> str:
    chars = [re.escape(char) for char in str(value or "").strip() if not char.isspace()]
    return r"\s*".join(chars) if chars else r"$^"


def fetch_neo4j_status(client, item_id: str | None) -> dict:
    if not item_id or not getattr(client, "available", False):
        return {"available": getattr(client, "available", False), "matches": []}

    def read(tx):
        if tx is None:
            return []
        return [
            dict(row)
            for row in tx.run(
                """
MATCH (item:MeetingItem {item_id: $item_id})
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (item)-[:HAS_COMPLETED_DATE]->(date:Date)
OPTIONAL MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       item.item_id AS item_id,
       item.actual_completed_date AS item_actual_completed_date,
       collect(DISTINCT date.date_value) AS completed_date_relations,
       action.action_id AS action_id,
       action.status AS action_status,
       action.status_source AS action_status_source,
       action.status_confidence AS action_status_confidence,
       action.actual_completed_date AS action_actual_completed_date,
       action.tracking_result AS action_tracking_result
""",
                item_id=item_id,
            )
        ]

    return {"available": True, "matches": client.execute_read(read)}
