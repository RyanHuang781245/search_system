from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

from apps.search.mongo import get_meeting_items_collection, get_meeting_minutes_collection

from . import cypher_queries as cq
from .keyword_extractor import extract_keyword_entities, extract_person_names


def build_graph_from_mongo(client) -> dict:
    meetings = list(get_meeting_minutes_collection().find({}, {"_id": 0}))
    items = list(get_meeting_items_collection().find({}, {"_id": 0}))
    items_by_meeting_id = defaultdict(list)
    for item in items:
        items_by_meeting_id[item.get("meeting_id")].append(item)

    keyword_pairs = Counter()
    node_counts = Counter()
    relation_counts = Counter()

    for meeting in meetings:
        document_id = meeting.get("document_id")
        meeting_id = meeting.get("meeting_id")
        original_filename = meeting.get("original_filename") or f"{document_id}.pdf"

        _write(client, _merge_document, document_id, original_filename)
        node_counts["Document"] += 1
        _write(client, _merge_meeting, meeting)
        node_counts["Meeting"] += 1
        _write(client, _merge_has_meeting, document_id, meeting_id)
        relation_counts["HAS_MEETING"] += 1

        unit_name = meeting.get("responsible_unit")
        if unit_name:
            _write(client, _merge_unit, unit_name)
            node_counts["Unit"] += 1
            _write(client, _merge_belongs_to_unit, meeting_id, unit_name)
            relation_counts["BELONGS_TO_UNIT"] += 1

        chairperson = str(meeting.get("chairperson") or "").strip()
        if chairperson:
            _write(client, _merge_person, chairperson)
            node_counts["Person"] += 1
            _write(client, _merge_chaired_by, meeting_id, chairperson)
            relation_counts["CHAIRED_BY"] += 1

        recorder = str(meeting.get("recorder") or "").strip()
        if recorder:
            _write(client, _merge_person, recorder)
            node_counts["Person"] += 1
            _write(client, _merge_recorded_by, meeting_id, recorder)
            relation_counts["RECORDED_BY"] += 1

        for attendee in extract_person_names(meeting):
            _write(client, _merge_person, attendee)
            node_counts["Person"] += 1
            _write(client, _merge_attended_by, meeting_id, attendee)
            relation_counts["ATTENDED_BY"] += 1

        _persist_keyword_mentions(
            client=client,
            owner_kind="meeting",
            owner_id=meeting_id,
            field="meeting_name",
            text=meeting.get("meeting_name"),
            node_counts=node_counts,
            relation_counts=relation_counts,
        )

        for item in items_by_meeting_id.get(meeting_id, []):
            item_id = item.get("item_id")
            _write(client, _merge_meeting_item, item)
            node_counts["MeetingItem"] += 1
            _write(client, _merge_has_item, meeting_id, item_id)
            relation_counts["HAS_ITEM"] += 1

            planned_date = _valid_text(item.get("planned_date"))
            if planned_date:
                _write(client, _merge_date, planned_date, "planned")
                node_counts["Date"] += 1
                _write(client, _merge_has_planned_date, item_id, planned_date)
                relation_counts["HAS_PLANNED_DATE"] += 1

            completed_date = _valid_text(item.get("actual_completed_date"))
            if completed_date:
                _write(client, _merge_date, completed_date, "completed")
                node_counts["Date"] += 1
                _write(client, _merge_has_completed_date, item_id, completed_date)
                relation_counts["HAS_COMPLETED_DATE"] += 1

            owner = str(item.get("owner") or "").strip()
            if owner and owner.lower() not in {"--", "na", "n/a", "none", "null"}:
                _write(client, _merge_person, owner)
                node_counts["Person"] += 1
                _write(client, _merge_responsible_by, item_id, owner)
                relation_counts["RESPONSIBLE_BY"] += 1

            keyword_names = []
            for field in ("content", "tracking_result"):
                keyword_names.extend(
                    _persist_keyword_mentions(
                        client=client,
                        owner_kind="item",
                        owner_id=item_id,
                        field=field,
                        text=item.get(field),
                        node_counts=node_counts,
                        relation_counts=relation_counts,
                    )
                )

            unique_keywords = sorted(set(keyword_names))
            for left, right in combinations(unique_keywords, 2):
                keyword_pairs[(left, right)] += 1
                keyword_pairs[(right, left)] += 1

    _persist_keyword_cooccurrence(client, keyword_pairs, relation_counts)

    return {
        "meeting_count": len(meetings),
        "item_count": len(items),
        "node_counts": dict(node_counts),
        "relationship_counts": dict(relation_counts),
    }


def _persist_keyword_cooccurrence(client, keyword_pairs: Counter, relation_counts: Counter) -> None:
    if not keyword_pairs:
        return

    max_per_keyword = defaultdict(int)
    for (left, _right), count in keyword_pairs.items():
        if count > max_per_keyword[left]:
            max_per_keyword[left] = count

    for (left, right), count in keyword_pairs.items():
        denominator = max_per_keyword[left] or 1
        weight = round(count / denominator, 4)
        _write(client, _merge_co_occurs_with, left, right, count, weight)
        relation_counts["CO_OCCURS_WITH"] += 1


def _write(client, callback, *args):
    if getattr(client, "available", False):
        return client.execute_write(callback, *args)
    return callback(None, *args)


def _persist_keyword_mentions(client, owner_kind, owner_id, field, text, node_counts, relation_counts):
    if not owner_id or not _valid_text(text):
        return []

    entities = extract_keyword_entities(text)
    keyword_names = []

    for keyword in entities["keywords"]:
        _write(client, _merge_keyword, keyword["name"], keyword["type"])
        node_counts["Keyword"] += 1
        if owner_kind == "meeting":
            _write(
                client,
                _merge_meeting_mentions_keyword,
                owner_id,
                keyword["name"],
                field,
                keyword.get("score", 0),
                keyword.get("method", "unknown"),
            )
        else:
            _write(
                client,
                _merge_mentions_keyword,
                owner_id,
                keyword["name"],
                field,
                keyword.get("score", 0),
                keyword.get("method", "unknown"),
            )
        relation_counts["MENTIONS"] += 1
        keyword_names.append(keyword["name"])

    if owner_kind == "item" and field == "content":
        for product in entities["products"]:
            _write(client, _merge_product, product)
            node_counts["Product"] += 1
            _write(client, _merge_mentions_product, owner_id, product)
            relation_counts["MENTIONS_PRODUCT"] += 1

        for regulation in entities["regulations"]:
            _write(client, _merge_regulation, regulation)
            node_counts["Regulation"] += 1
            _write(client, _merge_mentions_regulation, owner_id, regulation)
            relation_counts["MENTIONS_REGULATION"] += 1

    return keyword_names


def _valid_text(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower() in {"--", "na", "n/a", "none", "null"}:
        return None
    return text


def _merge_document(tx, document_id, original_filename):
    if tx is None:
        return None
    tx.run(cq.MERGE_DOCUMENT, document_id=document_id, original_filename=original_filename)


def _merge_meeting(tx, meeting):
    if tx is None:
        return None
    tx.run(
        cq.MERGE_MEETING,
        meeting_id=meeting.get("meeting_id"),
        meeting_name=meeting.get("meeting_name"),
        meeting_date=meeting.get("meeting_date"),
        responsible_unit=meeting.get("responsible_unit"),
    )


def _merge_has_meeting(tx, document_id, meeting_id):
    if tx is None:
        return None
    tx.run(cq.MERGE_HAS_MEETING, document_id=document_id, meeting_id=meeting_id)


def _merge_meeting_item(tx, item):
    if tx is None:
        return None
    tx.run(
        cq.MERGE_MEETING_ITEM,
        item_id=item.get("item_id"),
        item_no=item.get("item_no"),
        content=item.get("content"),
        planned_date=item.get("planned_date"),
        actual_completed_date=item.get("actual_completed_date"),
    )


def _merge_date(tx, date_value, date_type):
    if tx is None:
        return None
    tx.run(cq.MERGE_DATE, date_value=date_value, date_type=date_type)


def _merge_has_item(tx, meeting_id, item_id):
    if tx is None:
        return None
    tx.run(cq.MERGE_HAS_ITEM, meeting_id=meeting_id, item_id=item_id)


def _merge_has_planned_date(tx, item_id, date_value):
    if tx is None:
        return None
    tx.run(cq.MERGE_HAS_PLANNED_DATE, item_id=item_id, date_value=date_value)


def _merge_has_completed_date(tx, item_id, date_value):
    if tx is None:
        return None
    tx.run(cq.MERGE_HAS_COMPLETED_DATE, item_id=item_id, date_value=date_value)


def _merge_person(tx, name):
    if tx is None:
        return None
    tx.run(cq.MERGE_PERSON, name=name)


def _merge_unit(tx, name):
    if tx is None:
        return None
    tx.run(cq.MERGE_UNIT, name=name)


def _merge_chaired_by(tx, meeting_id, person_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_CHAIRED_BY, meeting_id=meeting_id, person_name=person_name)


def _merge_recorded_by(tx, meeting_id, person_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_RECORDED_BY, meeting_id=meeting_id, person_name=person_name)


def _merge_attended_by(tx, meeting_id, person_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_ATTENDED_BY, meeting_id=meeting_id, person_name=person_name)


def _merge_belongs_to_unit(tx, meeting_id, unit_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_BELONGS_TO_UNIT, meeting_id=meeting_id, unit_name=unit_name)


def _merge_responsible_by(tx, item_id, person_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_RESPONSIBLE_BY, item_id=item_id, person_name=person_name)


def _merge_keyword(tx, name, keyword_type):
    if tx is None:
        return None
    tx.run(cq.MERGE_KEYWORD, name=name, type=keyword_type)


def _merge_product(tx, name):
    if tx is None:
        return None
    tx.run(cq.MERGE_PRODUCT, name=name)


def _merge_regulation(tx, name):
    if tx is None:
        return None
    tx.run(cq.MERGE_REGULATION, name=name)


def _merge_mentions_keyword(tx, item_id, keyword_name, field, score, method):
    if tx is None:
        return None
    tx.run(
        cq.MERGE_MENTIONS_KEYWORD,
        item_id=item_id,
        keyword_name=keyword_name,
        field=field,
        score=score,
        method=method,
    )


def _merge_meeting_mentions_keyword(tx, meeting_id, keyword_name, field, score, method):
    if tx is None:
        return None
    tx.run(
        cq.MERGE_MEETING_MENTIONS_KEYWORD,
        meeting_id=meeting_id,
        keyword_name=keyword_name,
        field=field,
        score=score,
        method=method,
    )


def _merge_mentions_product(tx, item_id, product_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_MENTIONS_PRODUCT, item_id=item_id, product_name=product_name)


def _merge_mentions_regulation(tx, item_id, regulation_name):
    if tx is None:
        return None
    tx.run(cq.MERGE_MENTIONS_REGULATION, item_id=item_id, regulation_name=regulation_name)


def _merge_co_occurs_with(tx, left_keyword, right_keyword, count, weight):
    if tx is None:
        return None
    tx.run(
        cq.MERGE_CO_OCCURS_WITH,
        left_keyword=left_keyword,
        right_keyword=right_keyword,
        count=count,
        weight=weight,
    )
