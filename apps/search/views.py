from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import record_search_click, search_meeting_minutes


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
            return error_response("Page and limit must be valid integers.")

        data = search_meeting_minutes(
            q=request.GET.get("q"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
            responsible_unit=request.GET.get("responsible_unit"),
            owner=request.GET.get("owner"),
            chairperson=request.GET.get("chairperson"),
            status=request.GET.get("status"),
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
