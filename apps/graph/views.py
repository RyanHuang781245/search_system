from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .keyword_extractor import extract_keyword_entities
from .services import build_graph, expand_graph_node_query, get_related_keywords, graph_search_query, text2cypher_query


def success_response(data=None, message=None, status_code=status.HTTP_200_OK):
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message}, status=status_code)


class GraphBuildView(APIView):
    def post(self, request):
        data = build_graph()
        return success_response(data=data, message="Graph build completed.")


class RelatedKeywordView(APIView):
    def get(self, request, keyword):
        try:
            limit = max(int(request.GET.get("limit", 10)), 1)
        except (TypeError, ValueError):
            return error_response("limit must be a valid integer.")
        return success_response(data=get_related_keywords(keyword, limit=limit))


class GraphSearchView(APIView):
    def get(self, request):
        query = request.GET.get("q", "")
        if not str(query).strip():
            return error_response("q is required.")
        try:
            limit = max(int(request.GET.get("limit", 50)), 1)
        except (TypeError, ValueError):
            return error_response("limit must be a valid integer.")
        return success_response(data=graph_search_query(query, limit=limit))


class KeywordExtractView(APIView):
    def post(self, request):
        text = str(request.data.get("text", "")).strip()
        if not text:
            return error_response("text is required.")

        try:
            max_keywords = max(int(request.data.get("max_keywords", 12)), 1)
        except ValueError:
            return error_response("max_keywords must be a valid integer.")

        data = extract_keyword_entities(text, max_keywords=max_keywords)
        data["text"] = text
        data["keyword_count"] = len(data.get("keywords", []))
        return success_response(data=data)


class Text2CypherView(APIView):
    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if not question:
            return error_response("question is required.")
        try:
            limit = max(int(request.data.get("limit", 20)), 1)
        except (TypeError, ValueError):
            return error_response("limit must be a valid integer.")
        data = text2cypher_query(question, limit=limit)
        return success_response(data=data, message="Text2Cypher exploration completed.")


class GraphNodeExpandView(APIView):
    def post(self, request):
        node_id = str(request.data.get("node_id", "")).strip()
        if not node_id:
            return error_response("node_id is required.")
        try:
            limit = max(int(request.data.get("limit", 10)), 1)
        except (TypeError, ValueError):
            return error_response("limit must be a valid integer.")
        relation_scope = str(request.data.get("relation_scope", "default")).strip() or "default"
        data = expand_graph_node_query(node_id, limit=limit, relation_scope=relation_scope)
        return success_response(data=data, message="Graph node expansion completed.")
