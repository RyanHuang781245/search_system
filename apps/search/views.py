from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    get_related_items,
    get_related_meetings,
    get_stats,
    record_search_click,
    search_meeting_minutes,
)


def success_response(data=None, message=None, status_code=status.HTTP_200_OK):
    payload = {"success": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return Response(payload, status=status_code)


def error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"success": False, "message": message}, status=status_code)


class MeetingMinutesSearchView(APIView):
    def get(self, request):
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("page 和 limit 必須是有效整數。")

        try:
            has_owner = _parse_optional_bool(request.GET.get("has_owner"))
            has_planned_date = _parse_optional_bool(request.GET.get("has_planned_date"))
            is_completed = _parse_optional_bool(request.GET.get("is_completed"))
            has_tracking_result = _parse_optional_bool(request.GET.get("has_tracking_result"))
        except ValueError as error:
            return error_response(str(error))

        data = search_meeting_minutes(
            q=request.GET.get("q"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
            responsible_unit=request.GET.get("responsible_unit"),
            owner=request.GET.get("owner"),
            chairperson=request.GET.get("chairperson"),
            has_owner=has_owner,
            has_planned_date=has_planned_date,
            is_completed=is_completed,
            has_tracking_result=has_tracking_result,
            status=request.GET.get("status"),
            sort_by=request.GET.get("sort_by"),
            page=page,
            limit=limit,
        )
        return success_response(data=data, message="Search completed.")


class SearchClickLogView(APIView):
    def post(self, request):
        search_id = request.data.get("search_id")
        meeting_id = request.data.get("meeting_id")
        item_id = request.data.get("item_id")
        document_id = request.data.get("document_id")

        if not search_id or not meeting_id:
            return error_response("search_id and meeting_id are required.")

        click_log = record_search_click(
            search_id=search_id,
            meeting_id=meeting_id,
            item_id=item_id,
            document_id=document_id,
        )
        if not click_log:
            return error_response("Search log not found.", status.HTTP_404_NOT_FOUND)

        return success_response(data=click_log, message="Click logged.", status_code=status.HTTP_201_CREATED)


class RelatedMeetingsView(APIView):
    def get(self, request, meeting_id):
        try:
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("limit 必須是有效整數。")

        data = get_related_meetings(meeting_id, limit=limit)
        if not data:
            return error_response("Meeting not found.", status.HTTP_404_NOT_FOUND)
        return success_response(data=data)


class RelatedItemsView(APIView):
    def get(self, request, item_id):
        try:
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("limit 必須是有效整數。")

        data = get_related_items(item_id, limit=limit)
        if not data:
            return error_response("Item not found.", status.HTTP_404_NOT_FOUND)
        return success_response(data=data)


class SearchStatsView(APIView):
    def get(self, request):
        try:
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("limit 必須是有效整數。")
        return success_response(data=get_stats(limit=limit))


def _parse_optional_bool(value):
    if value in (None, ""):
        return None
    lowered = str(value).strip().lower()
    if lowered in {"true", "1", "yes"}:
        return True
    if lowered in {"false", "0", "no"}:
        return False
    raise ValueError("布林參數只接受 true 或 false。")
