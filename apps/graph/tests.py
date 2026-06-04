from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .graph_builder import build_graph_from_mongo
from .graph_search import fetch_related_keywords, search_graph
from .keyword_extractor import extract_keyword_entities


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

    def test_keyword_extract_endpoint_returns_scores_and_methods(self):
        response = self.client.post(
            reverse("graph-keyword-extract"),
            {
                "text": "Hydroxyapatite coating requires FDA label review and impingement risk evaluation.",
                "max_keywords": 8,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        keyword_names = [item["name"] for item in response.data["data"]["keywords"]]
        self.assertIn("FDA", keyword_names)
        self.assertTrue(
            any(name == "Hydroxyapatite coating" or name == "Hydroxyapatite" for name in keyword_names)
        )
        self.assertTrue(all("score" in item and "method" in item for item in response.data["data"]["keywords"]))


class KeywordExtractorTestCase(SimpleTestCase):
    def test_extract_keyword_entities_detects_regulation_product_and_chinese_terms(self):
        payload = extract_keyword_entities("Conformity stem 申請地區包含 FDA 與 TFDA，請確認標籤測試與送件需求。")

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertIn("Conformity stem", keyword_names)
        self.assertIn("FDA", keyword_names)
        self.assertIn("TFDA", keyword_names)
        self.assertIn("標籤", keyword_names)
        self.assertIn("送件", keyword_names)
        self.assertEqual(payload["products"], ["Conformity stem"])
        self.assertEqual(payload["regulations"], ["FDA", "TFDA"])

    def test_extract_keyword_entities_finds_new_terms_without_seed_list(self):
        payload = extract_keyword_entities("Hydroxyapatite coating 製程需評估內毒素與impingement風險。")

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertTrue(
            any(name == "Hydroxyapatite coating" or name == "Hydroxyapatite" for name in keyword_names)
        )
        self.assertTrue(any("內毒素" in name or "impingement" in name.lower() for name in keyword_names))
        self.assertTrue(all("score" in item and "method" in item for item in payload["keywords"]))


class GraphBuilderTestCase(SimpleTestCase):
    def test_build_graph_persists_dates_and_field_aware_mentions(self):
        meeting = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "meeting_name": "FDA 標籤確認會議",
            "meeting_date": "2018-04-03",
            "responsible_unit": "UR3",
            "chairperson": "倪仲達",
            "recorder": "倪仲達",
            "attendees": ["陳文全"],
        }
        item = {
            "item_id": "item_001",
            "meeting_id": "meeting_001",
            "item_no": "01",
            "content": "請UPD確認FDA標籤測試需求",
            "owner": "陳文全",
            "planned_date": "2018-04-20",
            "actual_completed_date": "2018-04-21",
            "tracking_result": "送件完成",
        }
        client = _CapturingGraphClient()

        with patch("apps.graph.graph_builder.get_meeting_minutes_collection", return_value=_FakeCollection([meeting])), patch(
            "apps.graph.graph_builder.get_meeting_items_collection", return_value=_FakeCollection([item])
        ):
            summary = build_graph_from_mongo(client)

        self.assertEqual(summary["node_counts"]["Date"], 2)
        self.assertEqual(summary["relationship_counts"]["HAS_PLANNED_DATE"], 1)
        self.assertEqual(summary["relationship_counts"]["HAS_COMPLETED_DATE"], 1)
        self.assertGreaterEqual(summary["relationship_counts"]["MENTIONS"], 3)

        date_params = [entry["params"] for entry in client.runs if "Date" in entry["query"]]
        self.assertIn({"date_value": "2018-04-20", "date_type": "planned"}, date_params)
        self.assertIn({"date_value": "2018-04-21", "date_type": "completed"}, date_params)

        mention_params = [
            entry["params"]
            for entry in client.runs
            if "MENTIONS" in entry["query"] and entry["params"].get("field")
        ]
        mention_fields = {params["field"] for params in mention_params}
        self.assertIn("meeting_name", mention_fields)
        self.assertIn("content", mention_fields)
        self.assertIn("tracking_result", mention_fields)
        self.assertTrue(all("score" in params and "method" in params for params in mention_params))


class _FakeGraphClient:
    available = True

    def execute_read(self, callback, *args):
        return callback(_FakeTx(), *args)


class _FakeCollection:
    def __init__(self, documents):
        self.documents = documents

    def find(self, *_args, **_kwargs):
        return list(self.documents)


class _CapturingGraphClient:
    available = True

    def __init__(self):
        self.runs = []

    def execute_write(self, callback, *args):
        return callback(_CapturingTx(self.runs), *args)


class _CapturingTx:
    def __init__(self, runs):
        self.runs = runs

    def run(self, query, **params):
        self.runs.append({"query": query, "params": params})


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

        if "MATCH (item:MeetingItem)-[mention:MENTIONS]->(keyword:Keyword)" in query and "FDA" in normalized_keywords:
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
                    "matched_field": "content",
                    "keyword_score": 1.0,
                    "keyword_method": "domain_abbreviation",
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
        self.assertEqual(payload["results"][0]["keyword_method"], "domain_abbreviation")
        self.assertGreater(payload["results"][0]["graph_score"], 0)
