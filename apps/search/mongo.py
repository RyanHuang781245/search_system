from pymongo import ASCENDING

from apps.documents.mongo import get_database


def get_meeting_minutes_collection():
    return get_database()["meeting_minutes"]


def get_meeting_items_collection():
    return get_database()["meeting_items"]


def get_search_logs_collection():
    return get_database()["search_logs"]


def get_search_click_logs_collection():
    return get_database()["search_click_logs"]


def ensure_indexes():
    get_meeting_minutes_collection().create_index(
        [("meeting_id", ASCENDING)],
        unique=True,
        name="uniq_meeting_id",
    )
    get_meeting_minutes_collection().create_index([("document_id", ASCENDING)], name="meeting_document_id")
    get_meeting_minutes_collection().create_index([("meeting_date", ASCENDING)], name="meeting_date")
    get_meeting_minutes_collection().create_index([("meeting_name", ASCENDING)], name="meeting_name")
    get_meeting_minutes_collection().create_index([("responsible_unit", ASCENDING)], name="meeting_responsible_unit")
    get_meeting_minutes_collection().create_index([("chairperson", ASCENDING)], name="meeting_chairperson")

    get_meeting_items_collection().create_index(
        [("item_id", ASCENDING)],
        unique=True,
        name="uniq_item_id",
    )
    get_meeting_items_collection().create_index([("meeting_id", ASCENDING)], name="item_meeting_id")
    get_meeting_items_collection().create_index([("document_id", ASCENDING)], name="item_document_id")
    get_meeting_items_collection().create_index([("owner", ASCENDING)], name="item_owner")
    get_meeting_items_collection().create_index([("planned_date", ASCENDING)], name="item_planned_date")
    get_meeting_items_collection().create_index([("content", ASCENDING)], name="item_content")

    get_search_logs_collection().create_index(
        [("search_id", ASCENDING)],
        unique=True,
        name="uniq_search_id",
    )
    get_search_logs_collection().create_index([("created_at", ASCENDING)], name="search_created_at")

    get_search_click_logs_collection().create_index(
        [("click_id", ASCENDING)],
        unique=True,
        name="uniq_click_id",
    )
    get_search_click_logs_collection().create_index([("search_id", ASCENDING)], name="click_search_id")
    get_search_click_logs_collection().create_index([("meeting_id", ASCENDING)], name="click_meeting_id")
    get_search_click_logs_collection().create_index([("item_id", ASCENDING)], name="click_item_id")
    get_search_click_logs_collection().create_index([("created_at", ASCENDING)], name="click_created_at")
