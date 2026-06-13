from __future__ import annotations

from .graph_builder import build_graph_from_mongo
from .graph_search import build_graph_score_context, fetch_related_keywords, search_graph
from .intent import analyze_graph_intent
from .neo4j_client import get_neo4j_client


def build_graph() -> dict:
    client = get_neo4j_client()
    result = build_graph_from_mongo(client)
    result["neo4j_available"] = getattr(client, "available", False)
    return result


def get_related_keywords(keyword: str, limit: int = 10) -> dict:
    client = get_neo4j_client()
    related = fetch_related_keywords(client, keyword, limit=limit)
    return {
        "keyword": keyword,
        "related_keywords": related,
    }


def graph_search_query(query: str, limit: int = 50) -> dict:
    client = get_neo4j_client()
    payload = search_graph(client, query, limit=limit, intent_analyzer=analyze_graph_intent)
    return {
        "query": payload["query"],
        "intent": payload.get("intent"),
        "intent_entities": payload.get("intent_entities", {}),
        "expanded_keywords": payload["expanded_keywords"],
        "results": payload["results"],
        "warnings": payload.get("warnings", []),
    }


def get_graph_score_context(query: str) -> dict:
    client = get_neo4j_client()
    return build_graph_score_context(client, query)
