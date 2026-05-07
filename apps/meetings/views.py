from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import (
    get_meeting_minutes_detail,
    list_meeting_items,
    list_meeting_minutes,
    parse_document_meeting_minutes,
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


class ParseMeetingMinutesView(APIView):
    def post(self, request, document_id):
        try:
            result = parse_document_meeting_minutes(document_id)
        except ValueError as exc:
            return error_response(str(exc))
        if not result:
            return error_response("Document not found.", status.HTTP_404_NOT_FOUND)
        if result["status"] == "needs_ocr":
            return success_response(
                data={
                    "document_id": document_id,
                    "status": "needs_ocr",
                },
                message="PDF text layer is insufficient and requires OCR.",
            )
        meeting = result["meeting_minutes"]
        return success_response(
            data={
                "meeting_id": meeting["meeting_id"],
                "meeting_name": meeting["meeting_name"],
                "meeting_date": meeting["meeting_date"],
                "item_count": len(result["meeting_items"]),
            },
            message="Meeting minutes parsed successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class MeetingMinutesListView(APIView):
    def get(self, request):
        data = list_meeting_minutes(
            keyword=request.GET.get("keyword"),
            meeting_name=request.GET.get("meeting_name"),
            date_from=request.GET.get("date_from"),
            date_to=request.GET.get("date_to"),
            responsible_unit=request.GET.get("responsible_unit"),
        )
        return success_response(data=data)


class MeetingMinutesDetailView(APIView):
    def get(self, request, meeting_id):
        data = get_meeting_minutes_detail(meeting_id)
        if not data:
            return error_response("Meeting minutes not found.", status.HTTP_404_NOT_FOUND)
        return success_response(data=data)


class MeetingItemsListView(APIView):
    def get(self, request):
        data = list_meeting_items(
            keyword=request.GET.get("keyword"),
            owner=request.GET.get("owner"),
            planned_date=request.GET.get("planned_date"),
            meeting_id=request.GET.get("meeting_id"),
        )
        return success_response(data=data)
