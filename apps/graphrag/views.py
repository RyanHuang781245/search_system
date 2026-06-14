from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import GraphRagServiceError, answer_question


def success_response(data=None, message=None, status_code=status.HTTP_200_OK):
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message}, status=status_code)


class GraphRagAskView(APIView):
    def post(self, request):
        question = str(request.data.get("question", "")).strip()
        if not question:
            return error_response("question is required.")

        limit = request.data.get("limit", "auto")
        if isinstance(limit, str):
            limit = limit.strip() or "auto"
        if not _is_valid_limit_value(limit):
            return error_response("limit must be auto, focused, balanced, broad, or a valid integer.")

        try:
            data = answer_question(question, limit=limit)
        except GraphRagServiceError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)

        return success_response(data=data, message="GraphRAG answer generated.")


def _is_valid_limit_value(value) -> bool:
    if value is None:
        return True
    if str(value).strip().lower() in {"auto", "focused", "precision", "balanced", "explore", "exploratory", "broad", "inventory", "wide"}:
        return True
    try:
        int(str(value).strip())
        return True
    except ValueError:
        return False
