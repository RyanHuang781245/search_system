from django.test import SimpleTestCase, override_settings

from apps.privacy.deidentification import (
    deidentify_document_record,
    deidentify_parsed_meeting_payload,
)


class PreWriteDeidentificationTestCase(SimpleTestCase):
    @override_settings(DEIDENTIFICATION_ENABLED=False)
    def test_deidentification_disabled_returns_payload_unchanged(self):
        document = {"document_id": "doc_001", "original_filename": "Alice minutes.pdf"}

        self.assertEqual(deidentify_document_record(document), document)

    @override_settings(DEIDENTIFICATION_ENABLED=True, DEIDENTIFICATION_SALT="test-salt", DEIDENTIFICATION_MAPPING_FILE="")
    def test_deidentifies_parsed_meeting_before_storage(self):
        parsed = {
            "status": "parsed",
            "meeting_minutes": {
                "meeting_id": "meeting_001",
                "document_id": "doc_001",
                "meeting_name": "Alice FDA review",
                "company_name": "Acme",
                "chairperson": "Alice",
                "recorder": "Bob",
                "responsible_unit": "UR3",
                "attendees": ["Alice", "Bob"],
                "raw_text": "Alice and Bob discussed FDA.",
            },
            "meeting_items": [
                {
                    "item_id": "item_001",
                    "meeting_id": "meeting_001",
                    "document_id": "doc_001",
                    "content": "Alice will confirm FDA requirements.",
                    "owner": "Alice",
                    "tracking_result": "Bob followed up.",
                    "raw_row_text": "Alice Bob FDA",
                }
            ],
            "raw_text": "Alice and Bob discussed FDA.",
        }

        payload = deidentify_parsed_meeting_payload(parsed)
        meeting = payload["meeting_minutes"]
        item = payload["meeting_items"][0]

        self.assertRegex(meeting["chairperson"], r"^Person_[A-F0-9]{10}$")
        self.assertRegex(meeting["recorder"], r"^Person_[A-F0-9]{10}$")
        self.assertRegex(meeting["responsible_unit"], r"^Unit_[A-F0-9]{10}$")
        self.assertRegex(item["owner"], r"^Person_[A-F0-9]{10}$")
        self.assertNotIn("Alice", item["content"])
        self.assertNotIn("Bob", item["tracking_result"])
        self.assertIn("person", item["content"])
        self.assertIn("FDA", item["content"])

    @override_settings(DEIDENTIFICATION_ENABLED=True, DEIDENTIFICATION_SALT="test-salt", DEIDENTIFICATION_MAPPING_FILE="")
    def test_deidentifies_document_filename_before_storage(self):
        document = {
            "document_id": "doc_001",
            "original_filename": "Alice minutes.pdf",
            "stored_filename": "doc_001.pdf",
            "file_path": "uploads/doc_001.pdf",
        }

        anonymized = deidentify_document_record(document)

        self.assertRegex(anonymized["original_filename"], r"^File_[A-F0-9]{10}\.pdf$")
        self.assertEqual(anonymized["stored_filename"], "doc_001.pdf")
        self.assertEqual(anonymized["file_path"], "uploads/doc_001.pdf")
