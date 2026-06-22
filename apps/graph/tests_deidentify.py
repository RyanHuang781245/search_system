import json
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from apps.graph.management.commands.deidentify_data import Pseudonymizer, anonymize_document, write_mapping_file


class DeidentifyDataTestCase(SimpleTestCase):
    def test_anonymize_document_preserves_system_paths_and_dates(self):
        pseudonymizer = Pseudonymizer(
            salt="test-salt",
            values={
                "person": {"Alice"},
                "unit": {"UR3"},
                "file": {"minutes.pdf"},
            },
        )
        document = {
            "document_id": "doc_20260621_abc123",
            "original_filename": "minutes.pdf",
            "stored_filename": "doc_20260621_abc123.pdf",
            "file_path": "uploads/doc_20260621_abc123.pdf",
            "meeting_date": "2018-04-03",
            "owner": "Alice",
            "responsible_unit": "UR3",
            "content": "Alice email alice@example.com phone 0912-345-678 on 2018-04-03",
        }

        anonymized = anonymize_document(document, pseudonymizer)

        self.assertEqual(anonymized["document_id"], document["document_id"])
        self.assertEqual(anonymized["stored_filename"], document["stored_filename"])
        self.assertEqual(anonymized["file_path"], document["file_path"])
        self.assertEqual(anonymized["meeting_date"], document["meeting_date"])
        self.assertNotEqual(anonymized["original_filename"], document["original_filename"])
        self.assertNotEqual(anonymized["owner"], document["owner"])
        self.assertNotEqual(anonymized["responsible_unit"], document["responsible_unit"])
        self.assertNotIn("Alice", anonymized["content"])
        self.assertNotIn("alice@example.com", anonymized["content"])
        self.assertNotIn("0912-345-678", anonymized["content"])
        self.assertIn("人員", anonymized["content"])
        self.assertIn("電子郵件", anonymized["content"])
        self.assertIn("電話", anonymized["content"])
        self.assertIn("2018-04-03", anonymized["content"])

    def test_write_mapping_file_contains_original_and_anonymized_values(self):
        pseudonymizer = Pseudonymizer(salt="test-salt", values={"person": {"Alice"}})
        pseudonymizer.text("Contact Alice at alice@example.com")

        with TemporaryDirectory() as temp_dir:
            path = f"{temp_dir}/mapping.json"
            summary = write_mapping_file(path, pseudonymizer, dry_run=True)
            payload = json.loads(open(path, encoding="utf-8").read())

        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(payload["record_count"], 2)
        records = {(row["kind"], row["original"]): row["anonymized"] for row in payload["records"]}
        self.assertIn(("person", "Alice"), records)
        self.assertIn(("email", "alice@example.com"), records)
