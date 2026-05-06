from pathlib import Path

from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from .services import (
    create_document_record,
    get_document_detail,
    list_documents,
    save_uploaded_file,
    soft_delete_document,
)
from .validators import (
    validate_file_extension,
    validate_file_not_empty,
    validate_file_size,
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


class DocumentUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            return error_response("File is required.")

        try:
            validate_file_not_empty(file_obj)
            validate_file_size(file_obj)
            validate_file_extension(file_obj)

            saved_file = save_uploaded_file(file_obj)
            document = create_document_record(
                file_obj=file_obj,
                doc_type=request.data.get("doc_type"),
                description=request.data.get("description", ""),
                tags=request.data.getlist("tags") or request.data.get("tags"),
                saved_file=saved_file,
                file_modified_at=request.data.get("file_modified_at"),
            )
        except ValidationError as exc:
            return error_response(_extract_error_message(exc))
        except Exception:
            if "saved_file" in locals():
                absolute_file_path = saved_file.get("absolute_file_path")
                if absolute_file_path:
                    path = Path(absolute_file_path)
                    if path.exists():
                        path.unlink()
            return error_response(
                "Failed to upload file.",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return success_response(
            data={
                "document_id": document["document_id"],
                "original_filename": document["original_filename"],
                "status": document["status"],
            },
            message="File uploaded successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class DocumentListView(APIView):
    def get(self, request):
        try:
            page = max(int(request.GET.get("page", 1)), 1)
            limit = max(int(request.GET.get("limit", 10)), 1)
        except ValueError:
            return error_response("Page and limit must be valid integers.")

        data = list_documents(
            keyword=request.GET.get("keyword"),
            doc_type=request.GET.get("doc_type"),
            status=request.GET.get("status"),
            page=page,
            limit=limit,
        )
        return success_response(data=data)


class DocumentDetailView(APIView):
    def get(self, request, document_id):
        document = get_document_detail(document_id)
        if not document:
            return error_response("Document not found.", status.HTTP_404_NOT_FOUND)
        return success_response(data=document)


class DocumentDeleteView(APIView):
    def delete(self, request, document_id):
        document = soft_delete_document(document_id)
        if not document:
            return error_response("Document not found.", status.HTTP_404_NOT_FOUND)
        return success_response(message="Document deleted successfully.")


class DocumentDetailDeleteView(APIView):
    def get(self, request, document_id):
        return DocumentDetailView().get(request, document_id)

    def delete(self, request, document_id):
        return DocumentDeleteView().delete(request, document_id)


def _extract_error_message(exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, list) and detail:
        return str(detail[0])
    if isinstance(detail, dict) and detail:
        first_value = next(iter(detail.values()))
        if isinstance(first_value, list) and first_value:
            return str(first_value[0])
        return str(first_value)
    return str(detail or exc)
