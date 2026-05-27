from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import build_graph, get_related_keywords, graph_search_query


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
        except ValueError:
            return error_response("limit must be a valid integer.")
        return success_response(data=get_related_keywords(keyword, limit=limit))


class GraphSearchView(APIView):
    def get(self, request):
        query = request.GET.get("q", "")
        if not str(query).strip():
            return error_response("q is required.")
        try:
            limit = max(int(request.GET.get("limit", 50)), 1)
        except ValueError:
            return error_response("limit must be a valid integer.")
        return success_response(data=graph_search_query(query, limit=limit))
