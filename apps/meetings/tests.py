from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from apps.documents import services as document_services


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)

    def sort(self, field, direction):
        reverse = direction == -1
        self.documents.sort(key=lambda item: item.get(field) or "", reverse=reverse)
        return self

    def skip(self, amount):
        self.documents = self.documents[amount:]
        return self

    def limit(self, amount):
        self.documents = self.documents[:amount]
        return self

    def __iter__(self):
        return iter(self.documents)


class FakeMongoCollection:
    def __init__(self):
        self.documents = []

    def insert_one(self, document):
        self.documents.append(dict(document))

    def insert_many(self, documents):
        self.documents.extend(dict(document) for document in documents)

    def delete_many(self, query):
        self.documents = [document for document in self.documents if not self._matches(document, query)]

    def update_one(self, query, update):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                updated = dict(document)
                updated.update(update.get("$set", {}))
                self.documents[index] = updated
                return

    def find(self, query, projection=None):
        results = [self._project(document, projection) for document in self.documents if self._matches(document, query)]
        return FakeCursor(results)

    def find_one(self, query, projection=None):
        for document in self.documents:
            if self._matches(document, query):
                return self._project(document, projection)
        return None

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

    def _matches(self, document, query):
        if not query:
            return True
        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches(document, clause) for clause in expected):
                    return False
                continue

            value = document.get(key)
            if isinstance(expected, dict):
                if "$regex" in expected:
                    if expected["$regex"].lower() not in str(value or "").lower():
                        return False
                    continue
                if "$elemMatch" in expected:
                    regex = expected["$elemMatch"].get("$regex", "")
                    options = expected["$elemMatch"].get("$options", "")
                    if "i" in options:
                        regex = regex.lower()
                        haystack = [str(item).lower() for item in value or []]
                    else:
                        haystack = [str(item) for item in value or []]
                    if not any(regex in item for item in haystack):
                        return False
                    continue
                if "$gte" in expected or "$lte" in expected:
                    if value is None:
                        return False
                    if "$gte" in expected and value < expected["$gte"]:
                        return False
                    if "$lte" in expected and value > expected["$lte"]:
                        return False
                    continue
            if value != expected:
                return False
        return True


class MeetingMinutesAPITestCase(APISimpleTestCase):
    def setUp(self):
        super().setUp()
        self.documents_collection = FakeMongoCollection()
        self.meeting_minutes_collection = FakeMongoCollection()
        self.meeting_items_collection = FakeMongoCollection()
        self.temp_dir = TemporaryDirectory()
        self.override = override_settings(UPLOAD_ROOT=Path(self.temp_dir.name))
        self.override.enable()
        self.patchers = [
            patch("apps.documents.services.get_documents_collection", return_value=self.documents_collection),
            patch("apps.meetings.services.get_documents_collection", return_value=self.documents_collection),
            patch("apps.meetings.services.get_meeting_minutes_collection", return_value=self.meeting_minutes_collection),
            patch("apps.meetings.services.get_meeting_items_collection", return_value=self.meeting_items_collection),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.override.disable()
        self.temp_dir.cleanup()
        super().tearDown()

    def test_parse_meeting_minutes_persists_minutes_and_items(self):
        document = self._create_document_from_sample("Meeting Minutes - Instrument.pdf")

        response = self.client.post(
            reverse("document-parse-meeting-minutes", args=[document["document_id"]])
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["meeting_date"], "2018-09-13")
        self.assertEqual(response.data["data"]["item_count"], 4)
        self.assertEqual(len(self.meeting_minutes_collection.documents), 1)
        self.assertEqual(len(self.meeting_items_collection.documents), 4)

        stored_meeting = self.meeting_minutes_collection.documents[0]
        self.assertEqual(stored_meeting["meeting_name"], "P1812 Coformity stem器械進度 會議")
        self.assertEqual(stored_meeting["location"], "台北會議室TP_A")
        self.assertEqual(stored_meeting["status"], "parsed")
        self.assertEqual(stored_meeting["page_count"], 1)

        first_item = self.meeting_items_collection.documents[0]
        self.assertEqual(first_item["item_no"], "01")
        self.assertIn("工程圖發出延後", first_item["content"])
        self.assertIsNone(first_item["owner"])

        updated_document = self.documents_collection.find_one({"document_id": document["document_id"]})
        self.assertEqual(updated_document["status"], "parsed")
        self.assertEqual(updated_document["page_count"], 1)

    def test_meeting_list_detail_and_item_filters_work_after_parse(self):
        document = self._create_document_from_sample("1. Meeting minutes.pdf")
        parse_response = self.client.post(
            reverse("document-parse-meeting-minutes", args=[document["document_id"]])
        )
        meeting_id = parse_response.data["data"]["meeting_id"]

        list_response = self.client.get(
            reverse("meeting-minutes-list"),
            {"meeting_name": "Conformity", "date_from": "2018-04-01", "date_to": "2018-04-30"},
        )
        detail_response = self.client.get(reverse("meeting-minutes-detail", args=[meeting_id]))
        items_response = self.client.get(
            reverse("meeting-items-list"),
            {"meeting_id": meeting_id, "owner": "倪仲達"},
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["data"]["total"], 1)
        self.assertEqual(
            list_response.data["data"]["meeting_minutes"][0]["meeting_name"],
            "Conformity stem 原型確認會議",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["data"]["meeting_minutes"]["meeting_id"], meeting_id)
        self.assertGreaterEqual(len(detail_response.data["data"]["meeting_items"]), 10)

        self.assertEqual(items_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(items_response.data["data"]["total"], 5)
        self.assertTrue(
            all(item["owner"] == "倪仲達" for item in items_response.data["data"]["meeting_items"])
        )

    def test_parse_blank_pdf_marks_document_as_needs_ocr(self):
        document = self._create_blank_pdf_document("blank_minutes.pdf")

        response = self.client.post(
            reverse("document-parse-meeting-minutes", args=[document["document_id"]])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["status"], "needs_ocr")
        self.assertEqual(self.meeting_minutes_collection.documents, [])
        self.assertEqual(self.meeting_items_collection.documents, [])

        updated_document = self.documents_collection.find_one({"document_id": document["document_id"]})
        self.assertEqual(updated_document["status"], "needs_ocr")

    def test_meeting_detail_serializes_naive_datetimes_without_error(self):
        self.meeting_minutes_collection.insert_one(
            {
                "meeting_id": "meeting_naive",
                "document_id": "doc_naive",
                "meeting_name": "Naive datetime meeting",
                "meeting_date": "2018-09-13",
                "attendees": [],
                "created_at": datetime(2026, 5, 6, 12, 0, 0),
                "updated_at": datetime(2026, 5, 6, 12, 30, 0),
            }
        )

        response = self.client.get(reverse("meeting-minutes-detail", args=["meeting_naive"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertIn("T", response.data["data"]["meeting_minutes"]["created_at"])
        self.assertIn("T", response.data["data"]["meeting_minutes"]["updated_at"])

    def _create_document_from_sample(self, sample_filename):
        sample_path = Path("pdf") / sample_filename
        upload_file = SimpleUploadedFile(
            sample_filename,
            sample_path.read_bytes(),
            content_type="application/pdf",
        )
        saved_file = document_services.save_uploaded_file(upload_file)
        return document_services.create_document_record(
            file_obj=upload_file,
            doc_type="meeting_minutes",
            saved_file=saved_file,
        )

    def _create_blank_pdf_document(self, filename):
        document = fitz.open()
        document.new_page()
        pdf_bytes = document.tobytes()
        document.close()

        upload_file = SimpleUploadedFile(
            filename,
            pdf_bytes,
            content_type="application/pdf",
        )
        saved_file = document_services.save_uploaded_file(upload_file)
        return document_services.create_document_record(
            file_obj=upload_file,
            doc_type="meeting_minutes",
            saved_file=saved_file,
        )
