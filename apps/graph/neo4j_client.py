from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

try:
    from neo4j import GraphDatabase
except Exception:  # pragma: no cover
    GraphDatabase = None


_neo4j_client = None


@dataclass
class DisabledNeo4jClient:
    available: bool = False

    def execute_write(self, callback, *args, **kwargs):
        return callback(None, *args, **kwargs) if callback else None

    def execute_read(self, callback, *args, **kwargs):
        return callback(None, *args, **kwargs) if callback else None

    def close(self):
        return None


class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str):
        self.database = database
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.available = True

    def execute_write(self, callback, *args, **kwargs):
        with self.driver.session(database=self.database) as session:
            return session.execute_write(callback, *args, **kwargs)

    def execute_read(self, callback, *args, **kwargs):
        with self.driver.session(database=self.database) as session:
            return session.execute_read(callback, *args, **kwargs)

    def close(self):
        self.driver.close()


def get_neo4j_client():
    global _neo4j_client
    if _neo4j_client is not None:
        return _neo4j_client

    if GraphDatabase is None:
        _neo4j_client = DisabledNeo4jClient()
        return _neo4j_client

    uri = getattr(settings, "NEO4J_URI", "")
    username = getattr(settings, "NEO4J_USERNAME", "")
    password = getattr(settings, "NEO4J_PASSWORD", "")
    database = getattr(settings, "NEO4J_DATABASE", "neo4j")

    if not uri or not username:
        _neo4j_client = DisabledNeo4jClient()
        return _neo4j_client

    try:
        _neo4j_client = Neo4jClient(uri, username, password, database)
    except Exception:
        _neo4j_client = DisabledNeo4jClient()
    return _neo4j_client


def reset_neo4j_client():
    global _neo4j_client
    if _neo4j_client is not None and hasattr(_neo4j_client, "close"):
        _neo4j_client.close()
    _neo4j_client = None
