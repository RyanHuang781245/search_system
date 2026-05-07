from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from . import services


class FakeInsertResult:
    inserted_id = "fake-id"


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction):
        reverse = direction == -1
        self.documents.sort(key=lambda item: item.get(field), reverse=reverse)
        return self

    def skip(self, amount):
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeDocumentsCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(dict(document))
        return FakeInsertResult()

    def count_documents(self, query):
        return len(self._filter(query))

    def find(self, query, projection=None):
        results = [self._project(document, projection) for document in self._filter(query)]
        return FakeCursor(results)

    def find_one(self, query, projection=None):
        matches = self._filter(query)
        if not matches:
            return None
        return self._project(matches[0], projection)

    def find_one_and_update(self, query, update, return_document=None, projection=None):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                return self._project(updated, projection)
        return None

    def update_one(self, query, update):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                return

    def _filter(self, query):
        return [dict(document) for document in self.documents if self._matches(document, query)]

    def _matches(self, document, query):
        for key, expected in query.items():
            value = document.get(key)
            if isinstance(expected, dict) and "$regex" in expected:
                keyword = expected["$regex"].lower()
                if keyword not in str(value or "").lower():
                    return False
            elif value != expected:
                return False
        return True

    def _project(self, document, projection):
        if not projection:
            return dict(document)

        include_fields = [key for key, value in projection.items() if value]
        exclude_fields = [key for key, value in projection.items() if not value]

        if include_fields:
            projected = {key: document[key] for key in include_fields if key in document}
        else:
            projected = dict(document)

        for field in exclude_fields:
            projected.pop(field, None)
        return projected


class DocumentAPITestCase(APISimpleTestCase):
    def setUp(self):
        super().setUp()
        self.collection = FakeDocumentsCollection()
        self.collection_patcher = patch(
            "apps.documents.services.get_documents_collection",
            return_value=self.collection,
        )
        self.collection_patcher.start()
        self.temp_dir = TemporaryDirectory()
        self.override = override_settings(UPLOAD_ROOT=Path(self.temp_dir.name))
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.temp_dir.cleanup()
        self.collection_patcher.stop()
        super().tearDown()

    def test_upload_pdf_creates_file_and_document_record(self):
        upload_file = SimpleUploadedFile(
            "test_report.pdf",
            b"%PDF-1.4 sample pdf content",
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("document-upload"),
            {
                "file": upload_file,
                "doc_type": "report",
                "description": "monthly report",
                "tags": ["finance", "monthly"],
                "file_modified_at": "2026-05-05T09:30:00+08:00",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["original_filename"], "test_report.pdf")
        self.assertEqual(response.data["data"]["status"], "uploaded")
        self.assertEqual(len(self.collection.documents), 1)

        stored_document = self.collection.documents[0]
        stored_path = Path(self.temp_dir.name) / stored_document["stored_filename"]
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_document["doc_type"], "report")
        self.assertEqual(stored_document["description"], "monthly report")
        self.assertEqual(stored_document["tags"], ["finance", "monthly"])
        self.assertEqual(stored_document["file_ext"], ".pdf")
        self.assertEqual(stored_document["status"], "uploaded")
        self.assertFalse(stored_document["is_deleted"])
        self.assertEqual(
            stored_document["file_modified_at"].isoformat(),
            "2026-05-05T09:30:00+08:00",
        )

    def test_upload_uses_client_provided_file_modified_at(self):
        upload_file = SimpleUploadedFile(
            "timed_report.pdf",
            b"%PDF-1.4 sample pdf content",
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("document-upload"),
            {
                "file": upload_file,
                "file_modified_at": "2026-05-05T09:30:00+08:00",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        stored_document = self.collection.documents[0]
        self.assertEqual(
            stored_document["file_modified_at"].isoformat(),
            "2026-05-05T09:30:00+08:00",
        )

    def test_upload_rejects_invalid_extension(self):
        upload_file = SimpleUploadedFile(
            "malware.exe",
            b"fake executable",
            content_type="application/octet-stream",
        )

        response = self.client.post(
            reverse("document-upload"),
            {"file": upload_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Dangerous file types", response.data["message"])
        self.assertEqual(self.collection.documents, [])

    def test_upload_rejects_empty_file(self):
        upload_file = SimpleUploadedFile(
            "empty.pdf",
            b"",
            content_type="application/pdf",
        )

        response = self.client.post(
            reverse("document-upload"),
            {"file": upload_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("Empty files", response.data["message"])

    def test_list_documents_excludes_soft_deleted_and_supports_filters(self):
        first_document = self._create_document("finance_report.pdf", doc_type="report")
        self._create_document("meeting_notes.docx", doc_type="memo")
        self._soft_delete(first_document["document_id"])

        response = self.client.get(
            reverse("document-list"),
            {"keyword": "meeting", "doc_type": "memo", "status": "uploaded"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["total"], 1)
        self.assertEqual(len(response.data["data"]["documents"]), 1)
        self.assertEqual(
            response.data["data"]["documents"][0]["original_filename"],
            "meeting_notes.docx",
        )

    def test_get_document_detail_returns_expected_fields(self):
        document = self._create_document(
            "contract.docx",
            doc_type="legal",
            description="signed",
            tags=["important"],
        )

        response = self.client.get(reverse("document-detail-delete", args=[document["document_id"]]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["document_id"], document["document_id"])
        self.assertEqual(response.data["data"]["original_filename"], "contract.docx")
        self.assertEqual(response.data["data"]["doc_type"], "legal")
        self.assertEqual(response.data["data"]["description"], "signed")
        self.assertEqual(response.data["data"]["tags"], ["important"])
        self.assertIn("file_modified_at", response.data["data"])

    def test_delete_document_soft_deletes_record(self):
        document = self._create_document("to_delete.pdf")

        response = self.client.delete(
            reverse("document-detail-delete", args=[document["document_id"]])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Document deleted successfully.")
        self.assertTrue(self.collection.documents[0]["is_deleted"])
        self.assertEqual(self.collection.documents[0]["status"], "deleted")
        self.assertIsNotNone(self.collection.documents[0]["deleted_at"])

    def test_deleted_document_does_not_appear_in_list_or_detail(self):
        document = self._create_document("archive.pdf")
        self._soft_delete(document["document_id"])

        list_response = self.client.get(reverse("document-list"))
        detail_response = self.client.get(
            reverse("document-detail-delete", args=[document["document_id"]])
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["data"]["total"], 0)
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(detail_response.data["success"])

    def test_delete_missing_document_returns_404(self):
        response = self.client.delete(
            reverse("document-detail-delete", args=["doc_20260505_missing"])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Document not found.")

    def test_list_returns_error_for_invalid_pagination_values(self):
        response = self.client.get(reverse("document-list"), {"page": "abc", "limit": "10"})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Page and limit must be valid integers.")

    def _create_document(self, filename, doc_type="unknown", description="", tags=None):
        content = b"document content"
        upload_file = SimpleUploadedFile(
            filename,
            content,
            content_type=self._content_type_for(filename),
        )
        saved_file = services.save_uploaded_file(upload_file)
        return services.create_document_record(
            file_obj=upload_file,
            doc_type=doc_type,
            description=description,
            tags=tags,
            saved_file=saved_file,
        )

    def _soft_delete(self, document_id):
        services.soft_delete_document(document_id)

    def _content_type_for(self, filename):
        extension = Path(filename).suffix.lower()
        if extension == ".pdf":
            return "application/pdf"
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
