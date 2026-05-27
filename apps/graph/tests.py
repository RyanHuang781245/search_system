from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .keyword_extractor import extract_keyword_entities
from .graph_search import fetch_related_keywords, search_graph


class GraphAPITestCase(APISimpleTestCase):
    def test_graph_build_endpoint_returns_summary(self):
        with patch(
            "apps.graph.views.build_graph",
            return_value={
                "meeting_count": 2,
                "item_count": 5,
                "node_counts": {"Meeting": 2, "MeetingItem": 5},
                "relationship_counts": {"HAS_ITEM": 5},
                "neo4j_available": True,
            },
        ):
            response = self.client.post(reverse("graph-build"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["meeting_count"], 2)

    def test_related_keyword_endpoint_returns_payload(self):
        with patch(
            "apps.graph.views.get_related_keywords",
            return_value={
                "keyword": "FDA",
                "related_keywords": [
                    {"keyword": "TFDA", "weight": 0.8, "count": 5},
                    {"keyword": "CFDA", "weight": 0.7, "count": 4},
                ],
            },
        ):
            response = self.client.get(reverse("graph-keyword-related", args=["FDA"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["keyword"], "FDA")
        self.assertEqual(response.data["data"]["related_keywords"][0]["keyword"], "TFDA")

    def test_graph_search_endpoint_returns_graph_matches(self):
        with patch(
            "apps.graph.views.graph_search_query",
            return_value={
                "query": "FDA",
                "expanded_keywords": ["TFDA", "CFDA"],
                "results": [
                    {
                        "meeting_id": "meet_001",
                        "item_id": "item_003",
                        "matched_keyword": "FDA",
                        "match_type": "direct",
                        "graph_score": 3.0,
                    }
                ],
            },
        ):
            response = self.client.get(reverse("graph-search"), {"q": "FDA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["expanded_keywords"], ["TFDA", "CFDA"])
        self.assertEqual(response.data["data"]["results"][0]["graph_score"], 3.0)


class KeywordExtractorTestCase(SimpleTestCase):
    def test_extract_keyword_entities_detects_regulation_product_and_chinese_terms(self):
        payload = extract_keyword_entities("Conformity stem 產品預計申請地區為 FDA、TFDA，並完成測試與送件。")

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertIn("Conformity stem", keyword_names)
        self.assertIn("FDA", keyword_names)
        self.assertIn("TFDA", keyword_names)
        self.assertIn("測試", keyword_names)
        self.assertIn("送件", keyword_names)
        self.assertEqual(payload["products"], ["Conformity stem"])
        self.assertEqual(payload["regulations"], ["FDA", "TFDA"])


class _FakeGraphClient:
    available = True

    def execute_read(self, callback, *args):
        return callback(_FakeTx(), *args)


class _FakeTx:
    def run(self, query, **params):
        normalized_keyword = str(params.get("keyword") or "").strip().upper()
        normalized_keywords = [str(item or "").strip().upper() for item in params.get("keywords", [])]

        if "CO_OCCURS_WITH" in query:
            if normalized_keyword == "FDA":
                return [
                    {"keyword": "TFDA", "type": "abbreviation", "weight": 1.0, "count": 2},
                    {"keyword": "CFDA", "type": "abbreviation", "weight": 0.5, "count": 1},
                ]
            return []

        if "MATCH (item:MeetingItem)-[:MENTIONS]->(keyword:Keyword)" in query and "FDA" in normalized_keywords:
            return [
                {
                    "meeting_id": "meet_001",
                    "meeting_name": "FDA 會議",
                    "meeting_date": "2018-04-03",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "提到 TFDA 與 FDA",
                    "matched_keyword": "TFDA",
                    "keyword_type": "abbreviation",
                }
            ]
        return []


class GraphSearchTestCase(SimpleTestCase):
    def test_fetch_related_keywords_is_case_insensitive(self):
        payload = fetch_related_keywords(_FakeGraphClient(), "fda", limit=10)

        self.assertEqual(payload[0]["keyword"], "TFDA")
        self.assertEqual(payload[1]["keyword"], "CFDA")

    def test_search_graph_expands_keywords_for_lowercase_query(self):
        payload = search_graph(_FakeGraphClient(), "fda", limit=10)

        self.assertEqual(payload["expanded_keywords"], ["TFDA", "CFDA"])
        self.assertEqual(payload["results"][0]["matched_keyword"], "TFDA")
        self.assertGreater(payload["results"][0]["graph_score"], 0)
