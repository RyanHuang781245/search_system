from pymongo import MongoClient
from django.conf import settings


_mongo_client = None


def get_mongo_client():
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(settings.MONGO_URI)
    return _mongo_client


def get_database():
    return get_mongo_client()[settings.MONGO_DB_NAME]


def get_documents_collection():
    return get_database()["documents"]


def reset_mongo_client():
    global _mongo_client
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None
