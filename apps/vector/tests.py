from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .services import build_meeting_item_embedding_text, index_meeting_items, semantic_search


class FakeCollection:
    def __init__(self, documents):
        self.documents = list(documents)

    def find(self, *_args, **_kwargs):
        return list(self.documents)


class FakeQdrantClient:
    def __init__(self):
        self.created_collections = []
        self.upserted_points = []
        self.search_results = []

    def get_collection(self, collection_name):
        raise Exception(f"Not found: {collection_name}")

    def create_collection(self, collection_name, vectors_config):
        self.created_collections.append(
            {"collection_name": collection_name, "vectors_config": vectors_config}
        )

    def upsert(self, collection_name, points):
        self.upserted_points.extend(points)

    def query_points(self, collection_name, query, limit):
        return self.search_results[:limit]


class VectorServiceTestCase(SimpleTestCase):
    @override_settings(QDRANT_COLLECTION_NAME="test_meeting_items", QDRANT_VECTOR_DIMENSION=3)
    def test_index_meeting_items_uses_meeting_item_payload(self):
        meeting = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "meeting_name": "FDA 標籤確認會議",
            "meeting_date": "2018-04-03",
            "responsible_unit": "UR3",
        }
        item = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "item_id": "item_001",
            "item_no": "01",
            "content": "請UPD確認FDA標籤測試需求",
            "owner": "陳文全",
            "planned_date": "2018-04-20",
            "actual_completed_date": None,
            "tracking_result": "送件完成",
        }
        client = FakeQdrantClient()

        with patch("apps.vector.services.get_meeting_minutes_collection", return_value=FakeCollection([meeting])), patch(
            "apps.vector.services.get_meeting_items_collection", return_value=FakeCollection([item])
        ):
            summary = index_meeting_items(
                client=client,
                embedder=lambda text: [0.1, 0.2, 0.3],
                batch_size=1,
            )

        self.assertEqual(summary["indexed_count"], 1)
        self.assertEqual(summary["skipped_count"], 0)
        self.assertEqual(client.created_collections[0]["collection_name"], "test_meeting_items")
        point = client.upserted_points[0]
        payload = getattr(point, "payload", None) or point["payload"]
        vector = getattr(point, "vector", None) or point["vector"]
        self.assertEqual(payload["document_id"], "doc_001")
        self.assertEqual(payload["meeting_id"], "meeting_001")
        self.assertEqual(payload["item_id"], "item_001")
        self.assertEqual(payload["item_no"], "01")
        self.assertEqual(payload["meeting_name"], "FDA 標籤確認會議")
        self.assertEqual(payload["status"], "pending")
        self.assertEqual(payload["status_confidence"], "low")
        self.assertIn("content: 請UPD確認FDA標籤測試需求", payload["embedding_text"])
        self.assertIn("status: pending", payload["embedding_text"])
        self.assertEqual(vector, [0.1, 0.2, 0.3])

    @override_settings(QDRANT_COLLECTION_NAME="test_meeting_items", QDRANT_VECTOR_DIMENSION=3)
    def test_semantic_search_serializes_payload_and_score(self):
        client = FakeQdrantClient()
        client.search_results = [
            {
                "score": 0.87,
                "payload": {
                    "document_id": "doc_001",
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "請UPD確認FDA標籤測試需求",
                },
            }
        ]

        payload = semantic_search(
            "FDA 標籤",
            client=client,
            embedder=lambda text: [0.1, 0.2, 0.3],
            limit=5,
        )

        self.assertEqual(payload["query"], "FDA 標籤")
        self.assertEqual(payload["results"][0]["item_id"], "item_001")
        self.assertEqual(payload["results"][0]["semantic_score"], 0.87)

    def test_embedding_text_contains_structured_fields(self):
        text = build_meeting_item_embedding_text(
            {"meeting_name": "設計審查", "meeting_date": "2018-04-03"},
            {"item_no": "01", "content": "確認標籤", "owner": "陳文全"},
        )

        self.assertIn("meeting_name: 設計審查", text)
        self.assertIn("item_no: 01", text)
        self.assertIn("owner: 陳文全", text)


class VectorAPITestCase(APISimpleTestCase):
    def test_reindex_endpoint_returns_summary(self):
        with patch(
            "apps.vector.views.index_meeting_items",
            return_value={
                "collection_name": "meeting_items",
                "indexed_count": 2,
                "skipped_count": 0,
            },
        ):
            response = self.client.post(reverse("vector-reindex"), {"batch_size": 2}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["indexed_count"], 2)

    def test_search_endpoint_requires_query(self):
        response = self.client.get(reverse("vector-search"))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def test_search_endpoint_returns_semantic_results(self):
        with patch(
            "apps.vector.views.semantic_search",
            return_value={
                "query": "FDA",
                "collection_name": "meeting_items",
                "results": [{"item_id": "item_001", "semantic_score": 0.9}],
            },
        ):
            response = self.client.get(reverse("vector-search"), {"q": "FDA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["results"][0]["item_id"], "item_001")
