from apps.documents.mongo import get_database


def get_meeting_minutes_collection():
    return get_database()["meeting_minutes"]


def get_meeting_items_collection():
    return get_database()["meeting_items"]
