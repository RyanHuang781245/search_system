from unittest.mock import patch

import json
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .evaluation import (
    evaluate_golden_cases,
    evaluate_payload,
    load_golden_cases,
    load_questions,
    save_approved_golden_cases,
    seed_golden_cases_from_questions,
    write_golden_cases,
)
from .deterministic import deterministic_query_understanding
from .query_router import analyze_query_route, route_question
from .services import (
    answer_question,
    augment_graph_results_with_structured_context,
    build_graph_context,
    build_graphrag_prompt,
    build_source_metadata_from_evidence,
    determine_effective_limit,
    graph_search_limit,
    meeting_items_structured_context,
    should_allow_keyword_fallback,
    validate_response_evidence_consistency,
)


class FakeCollection:
    def __init__(self, documents):
        self.documents = list(documents)

    def find(self, *_args, **_kwargs):
        return list(self.documents)


@override_settings(GRAPHRAG_QUERY_ROUTER_LLM_ENABLED=False)
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
                "label related overview",
                semantic_searcher=lambda question, limit: semantic_payload,
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "Carol owns item_001 from meeting_001.",
            )

        self.assertIn("item_001", payload["answer"])
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["limit_mode"], "manual")
        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["semantic"][0]["semantic_score"], 0.91)
        self.assertIn("Keyword(FDA)", payload["contexts"]["graph"]["paths"][0]["path"])
        self.assertEqual(payload["trace"]["route"]["query_type"], "keyword_exploration")
        self.assertEqual(payload["trace"]["context_counts"]["structured"], 1)
        self.assertTrue(payload["contexts"]["graph"]["nodes"])
        self.assertTrue(payload["contexts"]["graph"]["edges"])
        self.assertEqual(payload["sources"][0]["document_id"], "doc_001")
        self.assertEqual(payload["sources"][0]["content"], "UPD checks FDA label submission requirements.")
        self.assertEqual(payload["sources"][0]["evidence_source"], "neo4j")

    def test_answer_question_falls_back_to_evidence_claims_when_llm_returns_plain_text(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA label review meeting",
                "meeting_date": "2018-04-03",
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
                "tracking_result": None,
            }
        ]
        graph_payload = {
            "query": "FDA label related overview",
            "expanded_keywords": ["FDA"],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA label review meeting",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "UPD checks FDA label submission requirements.",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
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
                "FDA label related overview",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit: graph_payload,
                llm_client=lambda prompt: "This is plain text without evidence ids.",
            )

        self.assertIn("UPD checks FDA label submission requirements.", payload["answer"])
        self.assertEqual(payload["trace"]["answer_claims"]["evidence_ids"], ["evidence_001"])
        self.assertEqual([path["evidence_id"] for path in payload["contexts"]["graph"]["paths"]], ["evidence_001"])
        self.assertEqual([source["evidence_id"] for source in payload["sources"]], ["evidence_001"])
        self.assertTrue(validate_response_evidence_consistency(payload)["is_consistent"])

    def test_answer_question_uses_llm_evidence_selector_before_answering(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA label review meeting",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "Administrative note unrelated to FDA label evidence.",
            },
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_002",
                "item_no": "02",
                "content": "FDA label submission requires owner confirmation.",
            },
        ]
        graph_payload = {
            "query": "FDA label 摘要",
            "expanded_keywords": ["FDA"],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA label review meeting",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Administrative note unrelated to FDA label evidence.",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 2.0,
                },
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA label review meeting",
                    "item_id": "item_002",
                    "item_no": "02",
                    "content": "FDA label submission requires owner confirmation.",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 3.0,
                },
            ],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA label 摘要",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit, retrieval_modes=None: graph_payload,
                evidence_selector_client=lambda prompt: '{"selected_evidence_ids":["evidence_002"],"reason":"direct FDA label evidence"}',
                llm_client=lambda prompt: '{"claims":[{"claim":"FDA label submission requires owner confirmation.","evidence_ids":["evidence_002"]}]}',
                limit=5,
            )

        self.assertEqual(payload["trace"]["evidence"]["selection"]["mode"], "llm")
        self.assertEqual(payload["trace"]["evidence"]["candidate_count"], 2)
        self.assertEqual(payload["trace"]["evidence"]["selection"]["selected_evidence_ids"], ["evidence_002"])
        self.assertEqual([path["evidence_id"] for path in payload["contexts"]["graph"]["paths"]], ["evidence_002"])
        self.assertEqual([source["evidence_id"] for source in payload["sources"]], ["evidence_002"])
        self.assertIn("FDA label submission requires owner confirmation.", payload["answer"])
        self.assertNotIn("Administrative note", payload["answer"])

    def test_answer_question_uses_grounded_summary_text_when_requested(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Conformity stem review",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "陳聖昌負責工程圖變更與 FDA 優先送件安排。",
                "owner": "陳聖昌",
            },
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_002",
                "item_no": "02",
                "content": "陳聖昌協助確認器械時程。",
                "owner": "陳聖昌",
            },
        ]
        graph_payload = {
            "query": "陳聖昌負責哪些項目，幫我整理成摘要",
            "expanded_keywords": ["陳聖昌"],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Conformity stem review",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "陳聖昌負責工程圖變更與 FDA 優先送件安排。",
                    "matched_entity": "陳聖昌",
                    "matched_relation": "RESPONSIBLE_BY",
                    "match_type": "intent",
                    "graph_score": 4.0,
                },
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Conformity stem review",
                    "item_id": "item_002",
                    "item_no": "02",
                    "content": "陳聖昌協助確認器械時程。",
                    "matched_entity": "陳聖昌",
                    "matched_relation": "RESPONSIBLE_BY",
                    "match_type": "intent",
                    "graph_score": 4.0,
                },
            ],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "陳聖昌負責哪些項目，幫我整理成摘要",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit, retrieval_modes=None: graph_payload,
                llm_client=lambda prompt: (
                    '{"answer":"陳聖昌主要負責工程圖變更、FDA 優先送件安排，以及器械時程確認。",'
                    '"claims":['
                    '{"claim":"陳聖昌負責工程圖變更與 FDA 優先送件安排。","evidence_ids":["evidence_001"]},'
                    '{"claim":"陳聖昌協助確認器械時程。","evidence_ids":["evidence_002"]}'
                    ']}'
                ),
                limit="auto",
            )

        self.assertIn("陳聖昌主要負責工程圖變更、FDA 優先送件安排，以及器械時程確認。", payload["answer"])
        self.assertIn("依據：meeting_001 / item_001；meeting_001 / item_002", payload["answer"])
        self.assertEqual({path["evidence_id"] for path in payload["contexts"]["graph"]["paths"]}, {"evidence_001", "evidence_002"})
        self.assertEqual(payload["trace"]["answer_claims"]["evidence_ids"], ["evidence_001", "evidence_002"])

    def test_answer_question_keeps_candidates_when_evidence_selector_fails(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA label review meeting",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {"meeting_id": "meeting_001", "item_id": "item_001", "item_no": "01", "content": "First FDA item."},
            {"meeting_id": "meeting_001", "item_id": "item_002", "item_no": "02", "content": "Second FDA item."},
        ]
        graph_payload = {
            "query": "FDA 摘要",
            "expanded_keywords": ["FDA"],
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA label review meeting",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "First FDA item.",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 3.0,
                },
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA label review meeting",
                    "item_id": "item_002",
                    "item_no": "02",
                    "content": "Second FDA item.",
                    "matched_keyword": "FDA",
                    "matched_relation": "MENTIONS",
                    "matched_field": "content",
                    "match_type": "direct",
                    "graph_score": 3.0,
                },
            ],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA 摘要",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit, retrieval_modes=None: graph_payload,
                evidence_selector_client=lambda prompt: (_ for _ in ()).throw(RuntimeError("timeout")),
                llm_client=lambda prompt: "plain answer without claims",
                limit=5,
            )

        self.assertEqual(payload["trace"]["evidence"]["selection"]["mode"], "fallback_all")
        self.assertEqual(payload["trace"]["evidence"]["count"], 2)
        self.assertEqual([path["evidence_id"] for path in payload["contexts"]["graph"]["paths"]], ["evidence_001", "evidence_002"])
        self.assertTrue(any("Evidence selector unavailable" in warning for warning in payload["warnings"]))

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

    def test_answer_question_routes_structural_lists_without_semantic_search(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Owner review meeting",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "First meeting item.",
            },
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_002",
                "item_no": "02",
                "content": "Second meeting item.",
            },
        ]
        captured = {}

        def graph_searcher(question, limit, retrieval_modes=None):
            captured["limit"] = limit
            captured["retrieval_modes"] = retrieval_modes
            return {
                "query": question,
                "expanded_keywords": [],
                "results": [
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "Owner review meeting",
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "First meeting item.",
                        "matched_relation": "HAS_ITEM",
                        "matched_entity": "Owner review meeting",
                        "retrieval_mode": "structural",
                        "graph_score": 5.2,
                    },
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "Owner review meeting",
                        "item_id": "item_002",
                        "item_no": "02",
                        "content": "Second meeting item.",
                        "matched_relation": "HAS_ITEM",
                        "matched_entity": "Owner review meeting",
                        "retrieval_mode": "structural",
                        "graph_score": 5.2,
                    },
                ],
            }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "Which items are included in Owner review meeting?",
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run"),
                graph_searcher=graph_searcher,
                llm_client=lambda prompt: prompt,
                limit="auto",
            )

        self.assertEqual(payload["query_route"]["query_type"], "structural_list")
        self.assertEqual(captured["retrieval_modes"], ("structural",))
        self.assertEqual(captured["limit"], 50)
        self.assertEqual(len(payload["contexts"]["structured"]), 2)
        self.assertEqual(payload["contexts"]["semantic"], [])
        self.assertIn("First meeting item.", payload["answer"])
        self.assertIn("Second meeting item.", payload["answer"])
        self.assertEqual(payload["trace"]["answer_claims"]["evidence_ids"], ["evidence_001", "evidence_002"])

    def test_structural_list_falls_back_to_mongo_meeting_items_when_graph_misses(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "meeting_name": "P1812 Coformity stem 器械進度會議",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "item_id": "item_002",
                "item_no": "02",
                "content": "Second discussion item.",
            },
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "item_id": "item_001",
                "item_no": "01",
                "content": "First discussion item.",
            },
        ]

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "P1812 會議的討論事項",
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run"),
                graph_searcher=lambda question, limit, retrieval_modes=None: {"query": question, "results": []},
                llm_client=lambda prompt: "fallback answer",
                limit="auto",
            )

        self.assertEqual(payload["query_route"]["query_type"], "structural_list")
        self.assertEqual([item["item_id"] for item in payload["contexts"]["structured"]], ["item_001", "item_002"])
        self.assertEqual(payload["contexts"]["semantic"], [])
        trace_by_name = {retriever["name"]: retriever for retriever in payload["trace"]["retrievers"]}
        self.assertEqual(trace_by_name["graph"]["count"], 0)
        self.assertEqual(trace_by_name["mongo_structural_fallback"]["count"], 2)
        self.assertIn("First discussion item.", payload["answer"])
        self.assertIn("Second discussion item.", payload["answer"])

    def test_meeting_items_structured_context_matches_discussion_item_phrasing(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "meeting_name": "P1812 Coformity stem 器械進度會議",
            }
        ]
        items = [
            {"meeting_id": "meeting_p1812", "item_id": "item_001", "item_no": "01", "content": "First item."}
        ]

        context = meeting_items_structured_context("P1812 會議的討論事項", meetings, items, 50)

        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]["item_id"], "item_001")

    def test_meeting_items_structured_context_uses_llm_meeting_hint(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "meeting_name": "P1812 Coformity stem review",
            }
        ]
        items = [
            {"meeting_id": "meeting_p1812", "item_id": "item_001", "item_no": "01", "content": "First item."}
        ]

        context = meeting_items_structured_context("這場會議的討論事項", meetings, items, 50, meeting_hint="P1812")

        self.assertEqual(len(context), 1)
        self.assertEqual(context[0]["item_id"], "item_001")

    def test_answer_question_uses_llm_query_analyzer_route_and_entities(self):
        route = analyze_query_route(
            "這場會議的討論事項",
            llm_client=lambda _question: (
                '{"query_type":"structural_list","entities":{"meeting_hint":"P1812"}, "confidence":0.91}'
            ),
        )
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "meeting_name": "P1812 Coformity stem review",
            }
        ]
        items = [
            {"meeting_id": "meeting_p1812", "item_id": "item_001", "item_no": "01", "content": "First item."}
        ]

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "這場會議的討論事項",
                query_analyzer=lambda _question: route,
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run"),
                graph_searcher=lambda question, limit, retrieval_modes=None: {"query": question, "results": []},
                llm_client=lambda prompt: "answer",
                limit="auto",
            )

        self.assertEqual(payload["trace"]["route"]["route_source"], "llm")
        self.assertEqual(payload["trace"]["route"]["entities"]["meeting_hint"], "P1812")
        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["graph"]["paths"][0]["evidence_source"], "mongo_structural_fallback")
        self.assertIn("mongo_structural_fallback", payload["contexts"]["graph"]["paths"][0]["path"])

    def test_meeting_summary_uses_full_meeting_items_as_rag_evidence(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_p1812",
                "meeting_name": "P1812 Coformity stem器械進度 會議",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {"meeting_id": "meeting_p1812", "item_id": "item_001", "item_no": "01", "content": "工程圖發出延後，FDA優先。"},
            {"meeting_id": "meeting_p1812", "item_id": "item_002", "item_no": "02", "content": "Modular handle 需確認功能與材質。"},
        ]

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "P1812 Coformity stem器械進度 會議摘要",
                semantic_searcher=lambda question, limit: {"query": question, "results": []},
                graph_searcher=lambda question, limit, retrieval_modes=None: {"query": question, "results": []},
                llm_client=lambda _prompt: (
                    '{"claims":[{"claim":"本次會議重點是工程圖時程延後、FDA優先，以及 Modular handle 設計確認。",'
                    '"evidence_ids":["evidence_001","evidence_002"]}]}'
                ),
                limit="auto",
            )

        self.assertEqual(payload["query_route"]["query_type"], "meeting_summary")
        self.assertEqual(payload["limit_mode"], "auto:meeting_summary")
        self.assertEqual({item["item_id"] for item in payload["contexts"]["structured"]}, {"item_001", "item_002"})
        self.assertEqual({path["item_id"] for path in payload["contexts"]["graph"]["paths"]}, {"item_001", "item_002"})
        structural_trace = next(
            retriever for retriever in payload["trace"]["retrievers"] if retriever["name"] == "mongo_structural_fallback"
        )
        self.assertTrue(structural_trace["enabled"])
        self.assertEqual(structural_trace["count"], 2)
        self.assertIn("本次會議重點", payload["answer"])

    def test_semantic_summary_prefers_authoritative_graph_semantic_evidence(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA risk review",
            }
        ]
        items = [
            {
                "meeting_id": "meeting_001",
                "item_id": "item_risk",
                "item_no": "01",
                "content": "FDA submission delay risk needs owner review.",
            },
            {
                "meeting_id": "meeting_001",
                "item_id": "item_keyword",
                "item_no": "02",
                "content": "FDA label wording update.",
            },
            {
                "meeting_id": "meeting_001",
                "item_id": "item_vector",
                "item_no": "03",
                "content": "Vector-only similar context.",
            },
        ]
        graph_payload = {
            "query": "FDA 相關風險整理",
            "results": [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA risk review",
                    "item_id": "item_risk",
                    "item_no": "01",
                    "content": "FDA submission delay risk needs owner review.",
                    "matched_relation": "HAS_RISK",
                    "matched_entity": "FDA submission delay risk",
                    "retrieval_mode": "composite",
                    "graph_score": 4.9,
                }
            ],
        }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA 相關風險整理",
                semantic_searcher=lambda question, limit: {
                    "query": question,
                    "results": [
                        {"meeting_id": "meeting_001", "item_id": "item_vector", "content": "Vector-only similar context."}
                    ],
                },
                graph_searcher=lambda question, limit, retrieval_modes=None: graph_payload,
                llm_client=lambda _prompt: '{"claims":[]}',
                limit="auto",
            )

        self.assertEqual(payload["query_route"]["query_type"], "semantic_summary")
        self.assertEqual({item["item_id"] for item in payload["contexts"]["structured"]}, {"item_risk"})
        self.assertEqual(payload["contexts"]["semantic"], [])
        self.assertEqual({path["matched_relation"] for path in payload["contexts"]["graph"]["paths"]}, {"HAS_RISK"})
        keyword_trace = next(
            retriever for retriever in payload["trace"]["retrievers"] if retriever["name"] == "mongo_keyword_fallback"
        )
        self.assertFalse(keyword_trace["enabled"])
        self.assertTrue(validate_response_evidence_consistency(payload)["is_consistent"])

    def test_follow_up_tracking_uses_issue_timeline_as_authoritative_evidence(self):
        meetings = [
            {"document_id": "doc_001", "meeting_id": "meeting_001", "meeting_name": "FDA initial", "meeting_date": "2018-04-01"},
            {"document_id": "doc_002", "meeting_id": "meeting_002", "meeting_name": "FDA follow up", "meeting_date": "2018-04-08"},
        ]
        items = [
            {"meeting_id": "meeting_001", "item_id": "item_001", "item_no": "01", "content": "FDA issue is opened."},
            {"meeting_id": "meeting_002", "item_id": "item_002", "item_no": "02", "content": "FDA issue follow-up is updated."},
            {"meeting_id": "meeting_002", "item_id": "item_noise", "item_no": "03", "content": "Semantic noise."},
        ]
        captured = {}

        def graph_searcher(question, limit, retrieval_modes=None):
            captured["retrieval_modes"] = retrieval_modes
            return {
                "query": question,
                "results": [
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "FDA initial",
                        "meeting_date": "2018-04-01",
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "FDA issue is opened.",
                        "matched_relation": "TRACKS_ISSUE",
                        "matched_entity": "FDA issue",
                        "matched_node_id": "issue_fda",
                        "issue_id": "issue_fda",
                        "issue_title": "FDA issue",
                        "timeline_group": "issue_fda",
                        "sequence_no": 1,
                        "next_item_id": "item_002",
                        "retrieval_mode": "follow_up",
                        "graph_score": 4.7,
                        "evidence_relations": [
                            {
                                "source_type": "MeetingItem",
                                "source_value": "item_001",
                                "target_type": "Issue",
                                "target_value": "issue_fda",
                                "target_label": "FDA issue",
                                "relation": "TRACKS_ISSUE",
                            },
                            {
                                "source_type": "MeetingItem",
                                "source_value": "item_002",
                                "target_type": "MeetingItem",
                                "target_value": "item_001",
                                "relation": "FOLLOW_UP_OF",
                            },
                        ],
                    },
                    {
                        "meeting_id": "meeting_002",
                        "meeting_name": "FDA follow up",
                        "meeting_date": "2018-04-08",
                        "item_id": "item_002",
                        "item_no": "02",
                        "content": "FDA issue follow-up is updated.",
                        "matched_relation": "TRACKS_ISSUE",
                        "matched_entity": "FDA issue",
                        "matched_node_id": "issue_fda",
                        "issue_id": "issue_fda",
                        "issue_title": "FDA issue",
                        "timeline_group": "issue_fda",
                        "sequence_no": 2,
                        "previous_item_id": "item_001",
                        "retrieval_mode": "follow_up",
                        "graph_score": 4.7,
                        "evidence_relations": [
                            {
                                "source_type": "MeetingItem",
                                "source_value": "item_002",
                                "target_type": "Issue",
                                "target_value": "issue_fda",
                                "target_label": "FDA issue",
                                "relation": "TRACKS_ISSUE",
                            },
                            {
                                "source_type": "MeetingItem",
                                "source_value": "item_002",
                                "target_type": "MeetingItem",
                                "target_value": "item_001",
                                "relation": "FOLLOW_UP_OF",
                            },
                        ],
                    },
                ],
            }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "FDA 相關追蹤事項",
                semantic_searcher=lambda question, limit: {
                    "query": question,
                    "results": [
                        {"meeting_id": "meeting_002", "item_id": "item_noise", "content": "Semantic noise."}
                    ],
                },
                graph_searcher=graph_searcher,
                llm_client=lambda _prompt: '{"claims":[]}',
                limit="auto",
            )

        self.assertEqual(payload["query_route"]["query_type"], "follow_up_tracking")
        self.assertEqual(captured["retrieval_modes"], ("follow_up",))
        self.assertEqual({item["item_id"] for item in payload["contexts"]["structured"]}, {"item_001", "item_002"})
        self.assertEqual(payload["contexts"]["semantic"], [])
        self.assertEqual({path["matched_relation"] for path in payload["contexts"]["graph"]["paths"]}, {"TRACKS_ISSUE"})
        self.assertIn("FOLLOW_UP_OF", {edge["label"] for edge in payload["contexts"]["graph"]["edges"]})
        self.assertTrue(validate_response_evidence_consistency(payload)["is_consistent"])

    def test_answer_question_adds_structured_answer_items_to_evidence_graph(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Owner review meeting",
            }
        ]
        items = [
            {"meeting_id": "meeting_001", "item_id": "item_001", "item_no": "01", "content": "First item."}
        ]

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "Which items are included in Owner review meeting?",
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run"),
                graph_searcher=lambda question, limit, retrieval_modes=None: {"query": question, "results": []},
                llm_client=lambda prompt: "answer",
                limit="auto",
            )

        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["graph"]["paths"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["graph"]["paths"][0]["evidence_source"], "mongo_structural_fallback")

    def test_answer_question_uses_single_evidence_set_for_date_relation(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Due date review",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "Finish label review.",
                "planned_date": "2018-04-20",
            }
        ]

        def graph_searcher(question, limit, retrieval_modes=None):
            return {
                "query": question,
                "results": [
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "Due date review",
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "Finish label review.",
                        "matched_relation": "HAS_PLANNED_DATE",
                        "matched_entity": "2018-04-20",
                        "matched_field": "planned_date",
                        "retrieval_mode": "relation",
                        "graph_score": 4.0,
                    }
                ],
                "warnings": [],
            }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "2018-04-20 due items",
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run for date relation"),
                graph_searcher=graph_searcher,
                llm_client=lambda prompt: "answer",
                limit="auto",
            )

        self.assertEqual(payload["contexts"]["structured"][0]["item_id"], "item_001")
        self.assertEqual(payload["contexts"]["graph"]["paths"][0]["matched_relation"], "HAS_PLANNED_DATE")
        self.assertEqual(payload["sources"][0]["relation"], "HAS_PLANNED_DATE")
        self.assertEqual(payload["sources"][0]["evidence_source"], "neo4j")
        self.assertEqual(payload["trace"]["evidence"]["relations"]["HAS_PLANNED_DATE"], 1)

    def test_answer_question_completes_verified_claims_for_explicit_relation_queries(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "Due date review",
                "meeting_date": "2018-04-03",
            }
        ]
        items = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "item_no": "01",
                "content": "Finish label review.",
                "planned_date": "2018-04-20",
            },
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "item_id": "item_002",
                "item_no": "02",
                "content": "Prepare package.",
                "planned_date": "2018-04-20",
            },
        ]

        def graph_searcher(question, limit, retrieval_modes=None):
            return {
                "query": question,
                "results": [
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "Due date review",
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "Finish label review.",
                        "matched_relation": "HAS_PLANNED_DATE",
                        "matched_entity": "2018-04-20",
                        "matched_field": "planned_date",
                        "retrieval_mode": "relation",
                        "graph_score": 4.0,
                    },
                    {
                        "meeting_id": "meeting_001",
                        "meeting_name": "Due date review",
                        "item_id": "item_002",
                        "item_no": "02",
                        "content": "Prepare package.",
                        "matched_relation": "HAS_PLANNED_DATE",
                        "matched_entity": "2018-04-20",
                        "matched_field": "planned_date",
                        "retrieval_mode": "relation",
                        "graph_score": 4.0,
                    },
                ],
                "warnings": [],
            }

        with patch("apps.graphrag.services.get_meeting_minutes_collection", return_value=FakeCollection(meetings)), patch(
            "apps.graphrag.services.get_meeting_items_collection", return_value=FakeCollection(items)
        ):
            payload = answer_question(
                "2018-04-20 due items",
                semantic_searcher=lambda question, limit: self.fail("semantic search should not run for date relation"),
                graph_searcher=graph_searcher,
                llm_client=lambda prompt: '{"claims":[{"claim":"Finish label review.","evidence_ids":["evidence_001"]}]}',
                limit="auto",
            )

        self.assertIn("Finish label review.", payload["answer"])
        self.assertIn("Prepare package.", payload["answer"])
        self.assertEqual(
            [path["evidence_id"] for path in payload["contexts"]["graph"]["paths"]],
            ["evidence_001", "evidence_002"],
        )
        self.assertEqual([source["item_id"] for source in payload["sources"]], ["item_001", "item_002"])
        self.assertEqual(payload["trace"]["answer_claims"]["evidence_ids"], ["evidence_001", "evidence_002"])

    def test_augment_graph_results_keeps_neo4j_result_and_adds_missing_structured_items(self):
        payload = augment_graph_results_with_structured_context(
            graph_results=[
                {
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "matched_relation": "RESPONSIBLE_BY",
                    "matched_entity": "Carol",
                }
            ],
            structured_context=[
                {"meeting_id": "meeting_001", "meeting_name": "Meeting", "item_id": "item_001", "item_no": "01"},
                {"meeting_id": "meeting_001", "meeting_name": "Meeting", "item_id": "item_002", "item_no": "02"},
            ],
            semantic_results=[],
            structural_fallback_context=[],
            keyword_fallback_context=[
                {"meeting_id": "meeting_001", "item_id": "item_002"},
            ],
        )

        self.assertEqual(len(payload), 2)
        self.assertEqual(payload[0]["evidence_source"], "neo4j")
        self.assertEqual(payload[1]["item_id"], "item_002")
        self.assertEqual(payload[1]["evidence_source"], "mongo_keyword_fallback")

    def test_augment_graph_results_filters_unrelated_graph_candidates_when_answer_context_exists(self):
        payload = augment_graph_results_with_structured_context(
            graph_results=[
                {
                    "meeting_id": "meeting_wrong",
                    "meeting_name": "Wrong meeting",
                    "item_id": "item_wrong",
                    "item_no": "01",
                    "matched_relation": "HAS_COMPLETED_DATE",
                    "matched_entity": "2017-12-15",
                }
            ],
            structured_context=[
                {
                    "meeting_id": "meeting_right",
                    "meeting_name": "Right meeting",
                    "item_id": "item_right",
                    "item_no": "02",
                    "content": "Correct answer item.",
                }
            ],
            semantic_results=[],
            structural_fallback_context=[
                {"meeting_id": "meeting_right", "item_id": "item_right"},
            ],
            keyword_fallback_context=[],
        )

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["meeting_id"], "meeting_right")
        self.assertEqual(payload[0]["item_id"], "item_right")
        self.assertEqual(payload[0]["matched_relation"], "HAS_ITEM")
        self.assertEqual(payload[0]["evidence_source"], "mongo_structural_fallback")

    def test_augment_graph_results_keeps_graph_candidates_when_graph_is_only_context(self):
        payload = augment_graph_results_with_structured_context(
            graph_results=[
                {
                    "meeting_id": "meeting_graph",
                    "item_id": "item_graph",
                    "matched_relation": "MENTIONS",
                    "matched_entity": "FDA",
                }
            ],
            structured_context=[],
            semantic_results=[],
            structural_fallback_context=[],
            keyword_fallback_context=[],
        )

        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["item_id"], "item_graph")
        self.assertEqual(payload[0]["evidence_source"], "neo4j")

    def test_analyze_query_route_parses_llm_json(self):
        route = analyze_query_route(
            "P1812 那場會議有哪些討論事項",
            llm_client=lambda _question: (
                '{"query_type":"structural_list","entities":{"meeting_hint":"P1812"}, "confidence":0.88}'
            ),
        )

        self.assertEqual(route.query_type, "structural_list")
        self.assertEqual(route.route_source, "llm")
        self.assertEqual(route.entities["meeting_hint"], "P1812")
        self.assertEqual(route.confidence, 0.88)

    def test_analyze_query_route_uses_deterministic_route_without_llm_for_clear_questions(self):
        route = analyze_query_route("2017 年 12 月 15 日要完成哪些事項")

        self.assertEqual(route.query_type, "relation_lookup")
        self.assertEqual(route.route_source, "heuristic")
        self.assertEqual(route.entities["date_value"], "2017-12-15")
        self.assertEqual(route.warnings, ())

    def test_analyze_query_route_falls_back_for_invalid_llm_json(self):
        route = analyze_query_route("P1812 會議的討論事項", llm_client=lambda _question: "not json")

        self.assertEqual(route.query_type, "structural_list")
        self.assertEqual(route.route_source, "heuristic_fallback")
        self.assertTrue(route.warnings)

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
        self.assertNotIn("HAS_ACTION", edge_labels)
        self.assertIn("RESPONSIBLE_BY", edge_labels)
        self.assertIn("MENTIONS_REGULATION", edge_labels)
        node_types = {node["type"] for node in payload["nodes"]}
        self.assertNotIn("ActionItem", node_types)
        self.assertIn("RESPONSIBLE_BY", payload["paths"][0]["path"])
        self.assertIn("MENTIONS_REGULATION", payload["paths"][0]["path"])

    def test_graph_context_shows_semantic_nodes_for_semantic_routes(self):
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
                        }
                    ],
                }
            ],
            query_route=route_question("有哪些決議與風險"),
        )

        edge_labels = {edge["label"] for edge in payload["edges"]}
        node_types = {node["type"] for node in payload["nodes"]}
        self.assertIn("HAS_ACTION", edge_labels)
        self.assertIn("ActionItem", node_types)

    def test_source_metadata_preserves_relation_level_evidence_ids(self):
        records = [
            {
                "evidence_id": "evidence_001",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "relation": "MENTIONS_REGULATION",
                "evidence_source": "neo4j",
                "retrieved_by": "relation",
                "payload": {"document_id": "doc_001", "item_no": "01", "meeting_name": "FDA review"},
            },
            {
                "evidence_id": "evidence_002",
                "meeting_id": "meeting_001",
                "item_id": "item_001",
                "relation": "MENTIONS_REGULATION",
                "evidence_source": "neo4j",
                "retrieved_by": "relation",
                "payload": {"document_id": "doc_001", "item_no": "01", "meeting_name": "FDA review"},
            },
        ]

        sources = build_source_metadata_from_evidence(records)

        self.assertEqual([source["evidence_id"] for source in sources], ["evidence_001", "evidence_002"])

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
        self.assertEqual(payload["summary"]["total_paths"], 2)
        self.assertEqual(payload["summary"]["hidden_paths"], 1)
        self.assertTrue(payload["summary"]["is_truncated"])
        self.assertEqual(payload["summary"]["selection_mode"], "ranked_preview")
        self.assertIn("meeting_001", payload["paths"][0]["path"])
        self.assertNotIn("meeting_999", payload["paths"][0]["path"])
        item_nodes = [node for node in payload["nodes"] if node["type"] == "MeetingItem"]
        self.assertTrue(any("01\n" in node["label"] for node in item_nodes))

    def test_graph_context_force_complete_keeps_all_answer_evidence(self):
        results = [
            {
                "evidence_id": f"evidence_{index:03d}",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA review",
                "item_id": f"item_{index:03d}",
                "item_no": f"{index:02d}",
                "content": f"Evidence item {index}.",
                "matched_relation": "MENTIONS_REGULATION",
                "matched_entity": "FDA",
                "graph_score": 1.0,
            }
            for index in range(1, 9)
        ]

        payload = build_graph_context(results, limit=5, force_complete=True)

        self.assertEqual(len(payload["paths"]), 8)
        self.assertFalse(payload["summary"]["is_truncated"])
        self.assertEqual(payload["summary"]["selection_mode"], "answer_evidence")

    def test_graph_context_keeps_complete_relation_lookup_evidence(self):
        payload = build_graph_context(
            [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Owner review meeting",
                    "item_id": f"item_{index:03d}",
                    "item_no": f"{index:02d}",
                    "content": f"Owner item {index}",
                    "matched_relation": "RESPONSIBLE_BY",
                    "matched_entity": "Carol",
                    "retrieval_mode": "relation",
                    "graph_score": 4.0,
                }
                for index in range(1, 12)
            ],
            limit=6,
        )

        self.assertEqual(len(payload["paths"]), 11)
        self.assertEqual(payload["summary"]["total_paths"], 11)
        self.assertEqual(payload["summary"]["hidden_paths"], 0)
        self.assertFalse(payload["summary"]["is_truncated"])
        self.assertEqual(payload["summary"]["selection_mode"], "complete_evidence")

    def test_graph_context_keeps_more_has_item_paths_for_meeting_item_lists(self):
        payload = build_graph_context(
            [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Owner review meeting",
                    "item_id": f"item_{index:03d}",
                    "item_no": f"{index:02d}",
                    "content": f"Meeting item {index}",
                    "matched_relation": "HAS_ITEM",
                    "matched_entity": "Owner review meeting",
                    "graph_score": 5.2,
                }
                for index in range(1, 16)
            ],
            limit=50,
        )

        self.assertEqual(len(payload["paths"]), 15)
        self.assertEqual(payload["summary"]["total_paths"], 15)
        self.assertFalse(payload["summary"]["is_truncated"])
        self.assertTrue(all(path["matched_relation"] == "HAS_ITEM" for path in payload["paths"]))
        edge_labels = {edge["label"] for edge in payload["edges"]}
        self.assertEqual(edge_labels, {"HAS_ITEM"})

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
        self.assertTrue(payload["trace"]["is_insufficient"])
        self.assertEqual(payload["trace"]["context_counts"]["structured"], 0)
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
        self.assertEqual(determine_effective_limit("list all owner items", "auto"), (20, "auto:relation"))
        self.assertEqual(determine_effective_limit("FDA related status overview", "auto"), (20, "auto:relation"))
        self.assertEqual(determine_effective_limit("Is Carol responsible for FDA?", "auto"), (20, "auto:relation"))
        self.assertEqual(determine_effective_limit("Owner review meeting includes which items", "auto"), (50, "auto:structural_list"))
        self.assertEqual(determine_effective_limit("P1812 會議摘要", "auto"), (50, "auto:meeting_summary"))
        self.assertEqual(determine_effective_limit("manual", 15), (15, "manual"))
        self.assertEqual(determine_effective_limit("manual", "broad"), (12, "broad"))

    def test_query_router_classifies_core_question_types(self):
        self.assertEqual(route_question("Owner review meeting includes which items").query_type, "structural_list")
        self.assertEqual(route_question("P1812 會議的討論事項").query_type, "structural_list")
        self.assertEqual(route_question("P1812 會議有哪些議題").query_type, "structural_list")
        self.assertEqual(route_question("P1812 會議摘要").query_type, "meeting_summary")
        self.assertEqual(route_question("跨會議追蹤整理").query_type, "follow_up_tracking")
        self.assertEqual(route_question("FDA 相關追蹤事項").query_type, "follow_up_tracking")
        self.assertEqual(route_question("2017 年 12 月 15 日要完成哪些事項").query_type, "relation_lookup")
        self.assertEqual(route_question("Carol").query_type, "relation_lookup")
        self.assertEqual(route_question("廖漢星負責些會議項目").query_type, "relation_lookup")
        self.assertEqual(route_question("Carol FDA not completed items").query_type, "composite_query")
        self.assertEqual(route_question("FDA related status overview").query_type, "relation_lookup")

    def test_deterministic_query_understanding_extracts_core_entities(self):
        parsed = deterministic_query_understanding("陳聖昌 FDA Conformity stem 未完成事項")

        self.assertEqual(parsed["query_type"], "composite_query")
        self.assertEqual(parsed["graph_intent"], "person_responsibility")
        self.assertEqual(parsed["entities"]["person_name"], "陳聖昌")
        self.assertEqual(parsed["entities"]["regulation_name"].upper(), "FDA")
        self.assertEqual(parsed["entities"]["product_name"], "Conformity stem")
        self.assertEqual(parsed["entities"]["status"], "not_completed")

    def test_deterministic_query_understanding_routes_status_item_queries_to_composite(self):
        completed = deterministic_query_understanding("已完成的事項有哪些")
        not_applicable = deterministic_query_understanding("不適用的事項有哪些")

        self.assertEqual(completed["query_type"], "composite_query")
        self.assertEqual(completed["entities"]["status"], "completed")
        self.assertEqual(not_applicable["query_type"], "composite_query")
        self.assertEqual(not_applicable["entities"]["status"], "not_applicable")

    def test_deterministic_query_understanding_distinguishes_meeting_person_relations(self):
        cases = [
            ("陳聖昌出席哪些會議", "person_attendance"),
            ("陳聖昌主持哪些會議", "meeting_chair"),
            ("陳聖昌記錄哪些會議", "meeting_recorder"),
            ("陳聖昌負責哪些項目", "person_responsibility"),
        ]

        for question, intent in cases:
            with self.subTest(question=question):
                parsed = deterministic_query_understanding(question)
                self.assertEqual(parsed["query_type"], "relation_lookup")
                self.assertEqual(parsed["graph_intent"], intent)
                self.assertEqual(parsed["entities"]["person_name"], "陳聖昌")

    def test_deterministic_query_understanding_distinguishes_planned_and_completed_dates(self):
        planned = deterministic_query_understanding("2017 年 12 月 15 日要完成哪些事項")
        completed = deterministic_query_understanding("2017-12-15 實際完成哪些事項")

        self.assertEqual(planned["graph_intent"], "planned_date")
        self.assertEqual(planned["entities"]["date_value"], "2017-12-15")
        self.assertEqual(completed["graph_intent"], "completed_date")
        self.assertEqual(completed["entities"]["date_value"], "2017-12-15")

    def test_graph_search_limit_aligns_explicit_queries_with_answer_scope(self):
        self.assertEqual(graph_search_limit(route_question("Carol"), 20), 20)
        self.assertEqual(graph_search_limit(route_question("Carol FDA not completed items"), 15), 15)
        self.assertEqual(graph_search_limit(route_question("FDA 相關追蹤事項"), 30), 30)
        self.assertEqual(graph_search_limit(route_question("FDA related overview"), 10), 10)

    def test_pseudonym_person_responsibility_is_precise_relation_lookup(self):
        route = route_question("Person_366B42697E 負責什麼項目")
        parsed = deterministic_query_understanding("Person_366B42697E 負責什麼項目")

        self.assertEqual(parsed["query_type"], "relation_lookup")
        self.assertEqual(parsed["graph_intent"], "person_responsibility")
        self.assertEqual(parsed["entities"]["person_name"], "Person_366B42697E")
        self.assertEqual(route.query_type, "relation_lookup")
        self.assertEqual(route.entities["person_name"], "Person_366B42697E")
        self.assertFalse(should_allow_keyword_fallback(route, set()))


class GraphRagEvaluationTestCase(SimpleTestCase):
    def test_validate_response_evidence_consistency_passes_for_matching_ids(self):
        payload = {
            "trace": {"answer_claims": {"evidence_ids": ["evidence_001"]}},
            "contexts": {"graph": {"paths": [{"evidence_id": "evidence_001"}]}},
            "sources": [{"evidence_id": "evidence_001"}],
        }

        result = validate_response_evidence_consistency(payload)

        self.assertTrue(result["is_consistent"])
        self.assertEqual(result["errors"], [])

    def test_validate_response_evidence_consistency_detects_mismatch(self):
        payload = {
            "trace": {"answer_claims": {"evidence_ids": ["evidence_001"]}},
            "contexts": {"graph": {"paths": [{"evidence_id": "evidence_002"}]}},
            "sources": [{"evidence_id": "evidence_001"}],
        }

        result = validate_response_evidence_consistency(payload)

        self.assertFalse(result["is_consistent"])
        self.assertIn("graph evidence_ids do not match answer claim evidence_ids", result["errors"])

    def test_evaluate_payload_checks_expected_items_and_consistency(self):
        case = {
            "id": "date_case",
            "question": "2018-04-20 due items",
            "expected_item_ids": ["item_001"],
            "unexpected_item_ids": ["item_999"],
            "expected_relations": ["HAS_PLANNED_DATE"],
        }
        payload = {
            "answer": "Finish item_001.",
            "trace": {"answer_claims": {"evidence_ids": ["evidence_001"]}},
            "contexts": {
                "graph": {
                    "paths": [
                        {
                            "evidence_id": "evidence_001",
                            "item_id": "item_001",
                            "meeting_id": "meeting_001",
                            "matched_relation": "HAS_PLANNED_DATE",
                        }
                    ]
                }
            },
            "sources": [
                {
                    "evidence_id": "evidence_001",
                    "item_id": "item_001",
                    "meeting_id": "meeting_001",
                }
            ],
        }

        result = evaluate_payload(case, payload)

        self.assertEqual(result["status"], "passed")

    def test_evaluate_golden_cases_skips_disabled_cases(self):
        report = evaluate_golden_cases(
            [
                {"id": "disabled", "enabled": False, "question": "skip"},
                {"id": "enabled", "question": "run", "expected_item_ids": ["item_001"]},
            ],
            answerer=lambda question, limit="auto": {
                "answer": "item_001",
                "trace": {"answer_claims": {"evidence_ids": ["evidence_001"]}},
                "contexts": {"graph": {"paths": [{"evidence_id": "evidence_001", "item_id": "item_001"}]}},
                "sources": [{"evidence_id": "evidence_001", "item_id": "item_001"}],
            },
        )

        self.assertEqual(report["summary"]["skipped"], 1)
        self.assertEqual(report["summary"]["passed"], 1)

    def test_load_golden_cases_reads_cases_object(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump({"cases": [{"id": "case_001", "question": "q"}]}, handle)
            path = handle.name

        cases = load_golden_cases(path)

        self.assertEqual(cases[0]["id"], "case_001")

    def test_seed_golden_cases_from_questions_uses_observed_evidence(self):
        cases = seed_golden_cases_from_questions(
            ["2018-04-20 due items"],
            answerer=lambda question, limit="auto": {
                "answer": "item_001",
                "trace": {
                    "route": {"query_type": "relation_lookup"},
                    "answer_claims": {"evidence_ids": ["evidence_001"]},
                },
                "contexts": {
                    "graph": {
                        "paths": [
                            {
                                "evidence_id": "evidence_001",
                                "item_id": "item_001",
                                "meeting_id": "meeting_001",
                                "matched_relation": "HAS_PLANNED_DATE",
                            }
                        ]
                    }
                },
                "sources": [
                    {
                        "evidence_id": "evidence_001",
                        "item_id": "item_001",
                        "meeting_id": "meeting_001",
                    }
                ],
            },
        )

        self.assertFalse(cases[0]["enabled"])
        self.assertEqual(cases[0]["review_status"], "needs_review")
        self.assertEqual(cases[0]["expected_item_ids"], ["item_001"])
        self.assertEqual(cases[0]["expected_relations"], ["HAS_PLANNED_DATE"])
        self.assertTrue(cases[0]["observed"]["evidence_consistency"]["is_consistent"])

    def test_write_and_load_seeded_cases(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as handle:
            path = handle.name

        write_golden_cases([{"id": "case_001", "question": "q"}], path, description="test")
        cases = load_golden_cases(path)

        self.assertEqual(cases[0]["id"], "case_001")

    def test_save_approved_golden_cases_merges_by_id(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as handle:
            path = handle.name
        write_golden_cases(
            [
                {
                    "id": "case_001",
                    "enabled": True,
                    "question": "old",
                    "expected_item_ids": ["old_item"],
                }
            ],
            path,
        )

        result = save_approved_golden_cases(
            [
                {
                    "id": "case_001",
                    "enabled": True,
                    "question": "new",
                    "expected_item_ids": ["item_001"],
                    "expected_relations": ["HAS_ITEM"],
                },
                {
                    "id": "case_002",
                    "enabled": False,
                    "review_status": "needs_review",
                    "question": "skip",
                    "expected_item_ids": ["item_002"],
                },
            ],
            path,
        )

        cases = load_golden_cases(path)
        self.assertEqual(result["saved"], 1)
        self.assertEqual(result["updated"], 1)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["question"], "new")
        self.assertEqual(cases[0]["review_status"], "approved")

    def test_load_questions_reads_text_file(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as handle:
            handle.write("# comment\nquestion one\n\nquestion two\n")
            path = handle.name

        self.assertEqual(load_questions(path), ["question one", "question two"])

    def test_eval_graphrag_command_allows_empty_default_fixture(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump({"cases": [{"id": "disabled", "enabled": False, "question": "q"}]}, handle)
            path = handle.name

        call_command("eval_graphrag", cases=path, allow_empty=True)

    def test_seed_graphrag_cases_command_rejects_empty_questions_file(self):
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".txt", delete=False) as questions:
            questions.write("# empty\n")
            questions_path = questions.name
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as output:
            output_path = output.name

        with self.assertRaises(Exception):
            call_command("seed_graphrag_cases", questions=questions_path, out=output_path)


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

    def test_eval_seed_endpoint_returns_candidate_cases(self):
        with patch(
            "apps.graphrag.views.seed_golden_cases_from_questions",
            return_value=[{"id": "seed_001", "question": "q", "enabled": False}],
        ) as seed_cases:
            response = self.client.post(
                reverse("graphrag-eval-seed"),
                {"questions": "q\n", "limit": "auto"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["cases"][0]["id"], "seed_001")
        seed_cases.assert_called_once_with(["q"], enabled=False, limit="auto")

    def test_eval_seed_endpoint_requires_questions(self):
        response = self.client.post(reverse("graphrag-eval-seed"), {"questions": ""}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_eval_run_endpoint_returns_report(self):
        report = {"summary": {"passed": 1, "failed": 0, "skipped": 0, "enabled": 1}, "results": []}
        with patch("apps.graphrag.views.evaluate_golden_cases", return_value=report) as evaluate_cases:
            response = self.client.post(
                reverse("graphrag-eval-run"),
                {"cases": [{"id": "case_001", "question": "q"}]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["summary"]["passed"], 1)
        evaluate_cases.assert_called_once()

    def test_eval_run_endpoint_requires_cases(self):
        response = self.client.post(reverse("graphrag-eval-run"), {"cases": []}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_eval_save_endpoint_saves_approved_cases(self):
        with patch(
            "apps.graphrag.views.save_approved_golden_cases",
            return_value={"saved": 1, "created": 1, "updated": 0, "skipped": 0, "path": "cases.json"},
        ) as save_cases:
            response = self.client.post(
                reverse("graphrag-eval-save"),
                {"cases": [{"id": "case_001", "enabled": True, "question": "q", "expected_item_ids": ["item_001"]}]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["saved"], 1)
        save_cases.assert_called_once()

    def test_eval_save_endpoint_rejects_unapproved_cases(self):
        with patch(
            "apps.graphrag.views.save_approved_golden_cases",
            return_value={"saved": 0, "skipped": 1, "path": "cases.json"},
        ):
            response = self.client.post(
                reverse("graphrag-eval-save"),
                {"cases": [{"id": "case_001", "enabled": False, "question": "q"}]},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

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
