from __future__ import annotations

from .graph_builder import build_graph_from_mongo
from .graph_search import build_graph_score_context, fetch_related_keywords, search_graph
from .intent import analyze_graph_intent
from .neo4j_client import get_neo4j_client
from .query_planner import analyze_graph_query_plan
from .text2cypher import expand_graph_node, explore_text2cypher


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


def graph_search_query(query: str, limit: int = 50, retrieval_modes=None) -> dict:
    client = get_neo4j_client()
    payload = search_graph(
        client,
        query,
        limit=limit,
        retrieval_modes=retrieval_modes,
        intent_analyzer=analyze_graph_intent,
        query_planner=analyze_graph_query_plan,
    )
    return {
        "query": payload["query"],
        "query_plan": payload.get("query_plan", {}),
        "intent": payload.get("intent"),
        "intent_entities": payload.get("intent_entities", {}),
        "expanded_keywords": payload["expanded_keywords"],
        "retrieval_modes": payload.get("retrieval_modes", []),
        "results": payload["results"],
        "warnings": payload.get("warnings", []),
    }


def get_graph_score_context(query: str) -> dict:
    client = get_neo4j_client()
    return build_graph_score_context(client, query)


def text2cypher_query(question: str, limit: int = 20, llm_client=None) -> dict:
    client = get_neo4j_client()
    return explore_text2cypher(client, question, limit=limit, llm_client=llm_client)


def expand_graph_node_query(node_id: str, limit: int = 10, relation_scope: str = "default") -> dict:
    client = get_neo4j_client()
    return expand_graph_node(client, node_id=node_id, limit=limit, relation_scope=relation_scope)
