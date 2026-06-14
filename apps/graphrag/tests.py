from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .services import answer_question, build_graph_context, build_graphrag_prompt, determine_effective_limit


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
                "meeting_name": "FDA label review meeting",
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
                "content": "UPD checks FDA label submission requirements.",
                "owner": "Carol",
                "planned_date": "2018-04-20",
                "actual_completed_date": None,
                "tracking_result": "submission completed",
            }
        ]
        semantic_payload = {
            "query": "FDA label owner",
            "results": [
                {
                    "document_id": "doc_001",
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "item_no": "01",
                    "meeting_name": "FDA label review meeting",
                    "content": "UPD checks FDA label submission requirements.",
                    "semantic_score": 0.91,
                }
            ],
        }
        graph_payload = {
            "query": "FDA label owner",
            "expanded_keywords": ["label"],
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
                "FDA label owner",
                semantic_searcher=lambda question, limit: semantic_payload,
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "Carol owns item_001 from meeting_001.",
            )

        self.assertIn("Carol", payload["answer"])
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["limit_mode"], "manual")
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

    def test_graph_context_uses_supporting_evidence_relations(self):
        payload = build_graph_context(
            [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA review",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Carol handles FDA submission.",
                    "matched_relation": "HAS_ACTION",
                    "matched_entity": "Carol handles FDA submission.",
                    "matched_node_id": "action_item_001",
                    "evidence_relations": [
                        {
                            "source_type": "MeetingItem",
                            "source_value": "item_001",
                            "target_type": "ActionItem",
                            "target_value": "action_item_001",
                            "target_label": "Carol handles FDA submission.",
                            "relation": "HAS_ACTION",
                        },
                        {
                            "source_type": "MeetingItem",
                            "source_value": "item_001",
                            "target_type": "Person",
                            "target_value": "Carol",
                            "target_label": "Carol",
                            "relation": "RESPONSIBLE_BY",
                        },
                        {
                            "source_type": "MeetingItem",
                            "source_value": "item_001",
                            "target_type": "Regulation",
                            "target_value": "FDA",
                            "target_label": "FDA",
                            "relation": "MENTIONS_REGULATION",
                        },
                    ],
                }
            ]
        )

        edge_labels = {edge["label"] for edge in payload["edges"]}
        self.assertIn("HAS_ACTION", edge_labels)
        self.assertIn("RESPONSIBLE_BY", edge_labels)
        self.assertIn("MENTIONS_REGULATION", edge_labels)
        self.assertIn("RESPONSIBLE_BY", payload["paths"][0]["path"])
        self.assertIn("MENTIONS_REGULATION", payload["paths"][0]["path"])

    def test_graph_context_keeps_only_strong_evidence_results(self):
        payload = build_graph_context(
            [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Strong meeting",
                    "item_id": "item_strong_001",
                    "item_no": "01",
                    "content": "Strong FDA evidence.",
                    "matched_relation": "MENTIONS_REGULATION",
                    "matched_entity": "FDA",
                    "graph_score": 4.8,
                },
                {
                    "meeting_id": "meeting_999",
                    "meeting_name": "Weak unrelated meeting",
                    "item_id": "item_weak_001",
                    "item_no": "01",
                    "content": "Weak unrelated candidate.",
                    "matched_relation": "MENTIONS",
                    "matched_keyword": "related-only",
                    "graph_score": 1.0,
                },
            ],
            limit=10,
        )

        self.assertEqual(len(payload["paths"]), 1)
        self.assertIn("meeting_001", payload["paths"][0]["path"])
        self.assertNotIn("meeting_999", payload["paths"][0]["path"])
        item_nodes = [node for node in payload["nodes"] if node["type"] == "MeetingItem"]
        self.assertTrue(any("01\n" in node["label"] for node in item_nodes))

    def test_answer_question_returns_insufficient_data_message_without_context(self):
        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection([])), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection([])
        ):
            payload = answer_question(
                "unanswerable",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit: {"query": question, "results": []},
                llm_client=lambda prompt: "should not be called",
            )

        self.assertEqual(payload["answer"], "Insufficient meeting-record context to answer.")
        self.assertEqual(payload["sources"], [])

    def test_prompt_includes_source_grounding_rules(self):
        prompt = build_graphrag_prompt(
            question="What mentions FDA?",
            structured_context=[{"item_id": "item_001"}],
            graph_context={"paths": []},
            semantic_context=[],
            source_metadata=[{"item_id": "item_001"}],
        )

        self.assertIn("item_001", prompt)

    def test_determine_effective_limit_auto_scopes_questions(self):
        self.assertEqual(determine_effective_limit("list all owner items", "auto"), (12, "auto:broad"))
        self.assertEqual(determine_effective_limit("FDA related status overview", "auto"), (8, "auto:balanced"))
        self.assertEqual(determine_effective_limit("Is Carol responsible for FDA?", "auto"), (5, "auto:focused"))
        self.assertEqual(determine_effective_limit("manual", 15), (15, "manual"))
        self.assertEqual(determine_effective_limit("manual", "broad"), (12, "broad"))


class GraphRagAPITestCase(APISimpleTestCase):
    def test_ask_endpoint_requires_question(self):
        response = self.client.post(reverse("graphrag-ask"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def test_ask_endpoint_returns_answer(self):
        with patch(
            "apps.graphrag.views.answer_question",
            return_value={
                "question": "FDA owner",
                "limit": 3,
                "limit_mode": "manual",
                "answer": "item_001 has the owner.",
                "contexts": {"structured": [], "graph": {"paths": []}, "semantic": []},
                "sources": [{"item_id": "item_001"}],
                "warnings": [],
            },
        ):
            response = self.client.post(
                reverse("graphrag-ask"),
                {"question": "FDA owner", "limit": 3},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["answer"], "item_001 has the owner.")

    def test_ask_endpoint_accepts_auto_limit(self):
        with patch(
            "apps.graphrag.views.answer_question",
            return_value={
                "question": "inventory",
                "limit": 12,
                "limit_mode": "auto:broad",
                "answer": "answer",
                "contexts": {"structured": [], "graph": {"paths": []}, "semantic": []},
                "sources": [],
                "warnings": [],
            },
        ) as mocked_answer:
            response = self.client.post(
                reverse("graphrag-ask"),
                {"question": "inventory", "limit": "auto"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mocked_answer.assert_called_once_with("inventory", limit="auto")
        self.assertEqual(response.data["data"]["limit"], 12)
