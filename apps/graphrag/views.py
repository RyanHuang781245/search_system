from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .evaluation import evaluate_golden_cases, save_approved_golden_cases, seed_golden_cases_from_questions
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


class GraphRagEvalSeedView(APIView):
    def post(self, request):
        questions = _parse_questions(request.data.get("questions"))
        if not questions:
            return error_response("questions is required.")

        limit = request.data.get("limit", "auto")
        if isinstance(limit, str):
            limit = limit.strip() or "auto"
        if not _is_valid_limit_value(limit):
            return error_response("limit must be auto, focused, balanced, broad, or a valid integer.")

        try:
            cases = seed_golden_cases_from_questions(
                questions,
                enabled=bool(request.data.get("enabled", False)),
                limit=limit,
            )
        except GraphRagServiceError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return error_response(f"Unable to seed GraphRAG cases: {exc}", status.HTTP_503_SERVICE_UNAVAILABLE)

        return success_response(data={"cases": cases}, message="GraphRAG golden case candidates generated.")


class GraphRagEvalRunView(APIView):
    def post(self, request):
        cases = request.data.get("cases")
        if not isinstance(cases, list) or not cases:
            return error_response("cases must be a non-empty list.")

        try:
            report = evaluate_golden_cases(cases)
        except GraphRagServiceError as exc:
            return error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except Exception as exc:
            return error_response(f"Unable to evaluate GraphRAG cases: {exc}", status.HTTP_503_SERVICE_UNAVAILABLE)

        return success_response(data=report, message="GraphRAG evaluation completed.")


class GraphRagEvalSaveView(APIView):
    def post(self, request):
        cases = request.data.get("cases")
        if not isinstance(cases, list) or not cases:
            return error_response("cases must be a non-empty list.")

        try:
            result = save_approved_golden_cases(cases)
        except Exception as exc:
            return error_response(f"Unable to save GraphRAG golden cases: {exc}", status.HTTP_503_SERVICE_UNAVAILABLE)

        if result.get("saved", 0) == 0:
            return error_response("No approved cases to save. Mark cases as approved before saving.")

        return success_response(data=result, message="GraphRAG golden cases saved.")


def _parse_questions(value) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


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
