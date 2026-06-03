from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import VectorServiceError, index_meeting_items, semantic_search


def success_response(data=None, message=None, status_code=status.HTTP_200_OK):
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message}, status=status_code)


class VectorReindexView(APIView):
    def post(self, request):
        try:
            batch_size = max(int(request.data.get("batch_size", 64)), 1)
        except ValueError:
            return error_response("batch_size must be a valid integer.")

        try:
            data = index_meeting_items(batch_size=batch_size)
        except VectorServiceError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)

        return success_response(data=data, message="Vector index rebuilt.")


class VectorSearchView(APIView):
    def get(self, request):
        query = str(request.GET.get("q", "")).strip()
        if not query:
            return error_response("q is required.")
        try:
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("limit must be a valid integer.")

        try:
            data = semantic_search(query, limit=limit)
        except VectorServiceError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)

        return success_response(data=data)
