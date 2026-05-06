from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import SkipTest
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .mongo import get_documents_collection, get_mongo_client, reset_mongo_client


class DocumentMongoIntegrationTestCase(APISimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = TemporaryDirectory()
        cls.test_db_name = f"document_retrieval_system_test_{uuid4().hex[:8]}"
        cls.override = override_settings(
            UPLOAD_ROOT=Path(cls.temp_dir.name),
            MONGO_DB_NAME=cls.test_db_name,
        )
        cls.override.enable()
        reset_mongo_client()

        try:
            probe_client = MongoClient(
                settings.MONGO_URI,
                serverSelectionTimeoutMS=1000,
            )
            probe_client.admin.command("ping")
            probe_client.close()
        except PyMongoError as exc:
            cls.override.disable()
            cls.temp_dir.cleanup()
            raise SkipTest(f"MongoDB is not available for integration tests: {exc}")

    @classmethod
    def tearDownClass(cls):
        try:
            client = get_mongo_client()
            client.drop_database(cls.test_db_name)
        finally:
            reset_mongo_client()
            cls.override.disable()
            cls.temp_dir.cleanup()
            super().tearDownClass()

    def setUp(self):
        super().setUp()
        get_documents_collection().delete_many({})

    def test_upload_persists_file_and_metadata_in_real_mongodb(self):
        response = self.client.post(
            reverse("document-upload"),
            {
                "file": self._pdf_file("integration_report.pdf"),
                "doc_type": "report",
                "description": "integration test upload",
                "tags": ["alpha", "beta"],
                "file_modified_at": "2026-05-05T15:45:00+08:00",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])

        document_id = response.data["data"]["document_id"]
        stored_document = get_documents_collection().find_one({"document_id": document_id})

        self.assertIsNotNone(stored_document)
        self.assertEqual(stored_document["original_filename"], "integration_report.pdf")
        self.assertEqual(stored_document["doc_type"], "report")
        self.assertEqual(stored_document["description"], "integration test upload")
        self.assertEqual(stored_document["tags"], ["alpha", "beta"])
        self.assertEqual(stored_document["status"], "uploaded")
        self.assertFalse(stored_document["is_deleted"])
        self.assertEqual(
            stored_document["file_modified_at"].isoformat(),
            "2026-05-05T07:45:00",
        )

        stored_file = Path(self.temp_dir.name) / stored_document["stored_filename"]
        self.assertTrue(stored_file.exists())

        detail_response = self.client.get(reverse("document-detail-delete", args=[document_id]))
        self.assertEqual(
            detail_response.data["data"]["file_modified_at"],
            "2026-05-05T15:45:00+08:00",
        )

    def test_list_and_detail_read_from_real_mongodb(self):
        upload_response = self.client.post(
            reverse("document-upload"),
            {"file": self._docx_file("board_minutes.docx"), "doc_type": "minutes"},
            format="multipart",
        )
        document_id = upload_response.data["data"]["document_id"]

        list_response = self.client.get(
            reverse("document-list"),
            {"keyword": "board", "doc_type": "minutes", "status": "uploaded"},
        )
        detail_response = self.client.get(reverse("document-detail-delete", args=[document_id]))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["data"]["total"], 1)
        self.assertEqual(
            list_response.data["data"]["documents"][0]["original_filename"],
            "board_minutes.docx",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["data"]["document_id"], document_id)
        self.assertEqual(detail_response.data["data"]["doc_type"], "minutes")
        self.assertIn("file_modified_at", detail_response.data["data"])

    def test_delete_soft_deletes_real_mongodb_record_and_hides_it_from_queries(self):
        upload_response = self.client.post(
            reverse("document-upload"),
            {"file": self._pdf_file("delete_me.pdf")},
            format="multipart",
        )
        document_id = upload_response.data["data"]["document_id"]

        delete_response = self.client.delete(reverse("document-detail-delete", args=[document_id]))
        detail_response = self.client.get(reverse("document-detail-delete", args=[document_id]))
        list_response = self.client.get(reverse("document-list"))

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["data"]["total"], 0)

        stored_document = get_documents_collection().find_one({"document_id": document_id})
        self.assertIsNotNone(stored_document)
        self.assertTrue(stored_document["is_deleted"])
        self.assertEqual(stored_document["status"], "deleted")
        self.assertIsNotNone(stored_document["deleted_at"])

    def test_delete_missing_document_returns_404_with_real_mongodb(self):
        response = self.client.delete(
            reverse("document-detail-delete", args=["doc_20260505_missing"])
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["message"], "Document not found.")

    def _pdf_file(self, filename):
        return SimpleUploadedFile(
            filename,
            b"%PDF-1.4 integration pdf content",
            content_type="application/pdf",
        )

    def _docx_file(self, filename):
        return SimpleUploadedFile(
            filename,
            b"PK\x03\x04 integration docx content",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
