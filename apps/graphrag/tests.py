from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .services import answer_question, build_graphrag_prompt


class FakeCollection:
    def __init__(self, documents):
        self.documents = list(documents)

    def find(self, *_args, **_kwargs):
        return list(self.documents)


class GraphRagServiceTestCase(SimpleTestCase):
    def test_answer_question_combines_structured_graph_semantic_contexts(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA 標籤確認會議",
                "meeting_date": "2018-04-03",
                "responsible_unit": "UR3",
                "attendees": ["陳文全"],
            }
        ]
        items = [
            {
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
        ]

        semantic_payload = {
            "query": "FDA 標籤誰負責",
            "results": [
                {
                    "document_id": "doc_001",
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "item_no": "01",
                    "meeting_name": "FDA 標籤確認會議",
                    "content": "請UPD確認FDA標籤測試需求",
                    "semantic_score": 0.91,
                }
            ],
        }
        graph_payload = {
            "query": "FDA 標籤誰負責",
            "expanded_keywords": ["標籤"],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "matched_keyword": "FDA",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 3.0,
                }
            ],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA 標籤誰負責",
                semantic_searcher=lambda question, limit: semantic_payload,
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "item_001 由陳文全負責，來源 meeting_001 / item_001。",
            )

        self.assertIn("陳文全", payload["answer"])
        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["semantic"][0]["semantic_score"], 0.91)
        self.assertIn("Keyword(FDA)", payload["contexts"]["graph"]["paths"][0]["path"])
        self.assertTrue(payload["contexts"]["graph"]["nodes"])
        self.assertTrue(payload["contexts"]["graph"]["edges"])
        self.assertEqual(payload["sources"][0]["document_id"], "doc_001")

    def test_answer_question_prioritizes_intent_graph_matches_for_structured_context(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Owner review",
                "meeting_date": "2018-04-03",
                "responsible_unit": "UR3",
                "attendees": ["Carol"],
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "Prepare label submission.",
                "owner": "Carol",
                "planned_date": "2018-04-20",
                "actual_completed_date": None,
                "tracking_result": "In progress",
            }
        ]
        graph_payload = {
            "query": "Carol",
            "intent": "person_responsibility",
            "intent_entities": {"person_name": "Carol"},
            "expanded_keywords": [],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "matched_relation": "RESPONSIBLE_BY",
                    "matched_entity": "Carol",
                    "matched_field": "owner",
                    "match_type": "intent",
                    "intent": "person_responsibility",
                    "graph_score": 4.0,
                }
            ],
            "warnings": [],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "Carol",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "Carol is responsible for item_001.",
            )

        self.assertEqual(payload["contexts"]["structured"][0]["owner"], "Carol")
        self.assertIn("RESPONSIBLE_BY", payload["contexts"]["graph"]["paths"][0]["path"])
        node_types = {node["type"] for node in payload["contexts"]["graph"]["nodes"]}
        edge_labels = {edge["label"] for edge in payload["contexts"]["graph"]["edges"]}
        self.assertIn("Person", node_types)
        self.assertIn("RESPONSIBLE_BY", edge_labels)
        self.assertEqual(payload["warnings"], [])

    def test_answer_question_keeps_working_when_intent_warning_exists(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA review",
                "meeting_date": "2018-04-03",
                "responsible_unit": "UR3",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "FDA label submission.",
                "owner": "Carol",
            }
        ]
        graph_payload = {
            "query": "FDA",
            "expanded_keywords": [],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 3.0,
                }
            ],
            "warnings": ["Graph intent analysis unavailable: timeout"],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "FDA appears in item_001.",
            )

        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["warnings"], ["Graph intent analysis unavailable: timeout"])

    def test_answer_question_returns_insufficient_data_message_without_context(self):
        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection([])), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection([])
        ):
            payload = answer_question(
                "不存在的問題",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit: {"query": question, "results": []},
                llm_client=lambda prompt: "should not be called",
            )

        self.assertEqual(payload["answer"], "無法由現有會議記錄確認。")
        self.assertEqual(payload["sources"], [])

    def test_prompt_includes_source_grounding_rules(self):
        prompt = build_graphrag_prompt(
            question="誰負責 FDA?",
            structured_context=[{"item_id": "item_001"}],
            graph_context={"paths": []},
            semantic_context=[],
            source_metadata=[{"item_id": "item_001"}],
        )

        self.assertIn("只能根據", prompt)
        self.assertIn("item_001", prompt)


class GraphRagAPITestCase(APISimpleTestCase):
    def test_ask_endpoint_requires_question(self):
        response = self.client.post(reverse("graphrag-ask"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def test_ask_endpoint_returns_answer(self):
        with patch(
            "apps.graphrag.views.answer_question",
            return_value={
                "question": "FDA 誰負責",
                "answer": "item_001 由陳文全負責。",
                "contexts": {"structured": [], "graph": {"paths": []}, "semantic": []},
                "sources": [{"item_id": "item_001"}],
                "warnings": [],
            },
        ):
            response = self.client.post(
                reverse("graphrag-ask"),
                {"question": "FDA 誰負責", "limit": 3},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["answer"], "item_001 由陳文全負責。")
