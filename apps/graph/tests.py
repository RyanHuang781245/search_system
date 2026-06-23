from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from . import cypher_queries as cq
from .graph_builder import build_graph_from_mongo
from .graph_search import fetch_related_keywords, meeting_query_terms, search_graph
from .intent import analyze_graph_intent
from .keyword_extractor import extract_keyword_entities
from .query_planner import analyze_graph_query_plan, heuristic_query_plan
from .semantic_extractor import extract_responsible_people_from_text, extract_semantic_item
from .text2cypher import (
    build_text2cypher_graph,
    build_text2cypher_prompt,
    expand_graph_node,
    explore_text2cypher,
    template_cypher_for_question,
    text2cypher_expansion_query,
    validate_cypher,
)


@override_settings(KEYWORD_LLM_ENABLED=False, KEYWORD_EMBEDDING_RERANK_ENABLED=False)
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

    def test_text2cypher_endpoint_returns_exploration_payload(self):
        with patch(
            "apps.graph.views.text2cypher_query",
            return_value={
                "question": "哪些產品跨最多會議被討論？",
                "cypher": "MATCH (i:MeetingItem)-[:MENTIONS_PRODUCT]->(p:Product) RETURN p.name AS product LIMIT 5",
                "rows": [{"product": "Conformity stem"}],
                "row_count": 1,
                "blocked": False,
                "warnings": [],
            },
        ):
            response = self.client.post(
                reverse("graph-text2cypher"),
                {"question": "哪些產品跨最多會議被討論？", "limit": 5},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["data"]["blocked"])
        self.assertEqual(response.data["data"]["rows"][0]["product"], "Conformity stem")

    def test_graph_node_expand_endpoint_returns_graph_payload(self):
        with patch(
            "apps.graph.views.expand_graph_node_query",
            return_value={
                "node_id": "Date:2017-12-15",
                "graph": {
                    "nodes": [{"id": "Date:2017-12-15", "type": "Date", "label": "2017-12-15"}],
                    "edges": [],
                    "summary": {"projection": "manual_node_expansion"},
                },
                "warnings": [],
            },
        ):
            response = self.client.post(
                reverse("graph-node-expand"),
                {"node_id": "Date:2017-12-15", "limit": 5},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["node_id"], "Date:2017-12-15")
        self.assertEqual(response.data["data"]["graph"]["summary"]["projection"], "manual_node_expansion")


@override_settings(KEYWORD_LLM_ENABLED=False, KEYWORD_EMBEDDING_RERANK_ENABLED=False)
class KeywordExtractorFallbackTestCase(SimpleTestCase):
    def test_extract_keyword_entities_uses_regex_and_jieba_without_domain_list(self):
        payload = extract_keyword_entities(
            "Conformity stem application includes FDA and TFDA label submission checks."
        )

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertIn("Conformity stem", keyword_names)
        self.assertIn("FDA", keyword_names)
        self.assertIn("TFDA", keyword_names)
        self.assertEqual(payload["products"], ["Conformity stem"])
        self.assertEqual(payload["regulations"], ["FDA", "TFDA"])
        self.assertFalse(any(item["method"].startswith("domain_") for item in payload["keywords"]))

    def test_extract_keyword_entities_finds_new_terms_without_seed_list(self):
        payload = extract_keyword_entities("Hydroxyapatite coating needs impingement risk evaluation.")

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertTrue(
            any(name == "Hydroxyapatite coating" or name == "Hydroxyapatite" for name in keyword_names)
        )
        self.assertTrue(any("impingement" in name.lower() for name in keyword_names))
        self.assertTrue(all("score" in item and "method" in item for item in payload["keywords"]))


class KeywordLlmEmbeddingTestCase(SimpleTestCase):
    @override_settings(KEYWORD_LLM_ENABLED=True, KEYWORD_EMBEDDING_RERANK_ENABLED=False)
    def test_extract_keyword_entities_uses_llm_candidates_for_new_terms(self):
        def fake_llm(_source, max_keywords):
            return [
                {"name": "acetabular locking mechanism", "type": "technical_term", "score": 0.91},
                {"name": "custom trial implant", "type": "product", "score": 0.88},
            ][:max_keywords]

        payload = extract_keyword_entities(
            "The new design mentions acetabular locking mechanism and custom trial implant validation.",
            llm_client=fake_llm,
        )

        keyword_names = [item["name"] for item in payload["keywords"]]
        self.assertIn("acetabular locking mechanism", keyword_names)
        self.assertIn("custom trial implant", keyword_names)
        self.assertTrue(
            any(item["method"] == "ollama_llm" for item in payload["keywords"] if item["name"] == "custom trial implant")
        )

    @override_settings(KEYWORD_LLM_ENABLED=False, KEYWORD_EMBEDDING_RERANK_ENABLED=True)
    def test_extract_keyword_entities_can_rerank_with_embeddings(self):
        vectors = {
            "FDA label submission check": [1.0, 0.0, 0.0],
            "FDA": [1.0, 0.0, 0.0],
        }

        def fake_embedder(value):
            return vectors.get(value, [0.2, 0.8, 0.0])

        payload = extract_keyword_entities("FDA label submission check", embedder=fake_embedder)

        fda = next(item for item in payload["keywords"] if item["name"] == "FDA")
        self.assertIn("embedding_rerank", fda["method"])


@override_settings(KEYWORD_LLM_ENABLED=False, KEYWORD_EMBEDDING_RERANK_ENABLED=False)
class GraphBuilderTestCase(SimpleTestCase):
    def test_build_graph_persists_dates_and_field_aware_mentions(self):
        meeting = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "meeting_name": "FDA label review meeting",
            "meeting_date": "2018-04-03",
            "responsible_unit": "UR3",
            "chairperson": "Alice",
            "recorder": "Bob",
            "attendees": ["Carol"],
        }
        item = {
            "item_id": "item_001",
            "meeting_id": "meeting_001",
            "item_no": "01",
            "content": "UPD checks FDA label submission requirements.",
            "owner": "Carol",
            "planned_date": "2018-04-20",
            "actual_completed_date": "2018-04-21",
            "tracking_result": "FDA tracking result completed.",
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
        self.assertTrue(all(not str(params["method"]).startswith("domain_") for params in mention_params))

    def test_build_graph_clears_stale_completed_date_relation_for_placeholder_date(self):
        meeting = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "meeting_name": "Design transfer",
            "meeting_date": "2018-04-03",
        }
        item = {
            "item_id": "item_001",
            "meeting_id": "meeting_001",
            "item_no": "05",
            "content": "可用性評估報告確認",
            "owner": "UR3",
            "planned_date": "--",
            "actual_completed_date": "--",
            "tracking_result": "不 適 用 ，詳 設 計 移 轉 會 議 投 影 片 ( 附 件)",
        }
        client = _CapturingGraphClient()

        with patch("apps.graph.graph_builder.get_meeting_minutes_collection", return_value=_FakeCollection([meeting])), patch(
            "apps.graph.graph_builder.get_meeting_items_collection", return_value=_FakeCollection([item])
        ):
            summary = build_graph_from_mongo(client)

        self.assertEqual(summary["relationship_counts"].get("HAS_COMPLETED_DATE", 0), 0)
        self.assertEqual(summary["relationship_counts"].get("HAS_PLANNED_DATE", 0), 0)
        completed_date_merges = [
            entry for entry in client.runs
            if "MERGE (i)-[:HAS_COMPLETED_DATE]->(d)" in entry["query"]
        ]
        self.assertEqual(completed_date_merges, [])
        cleanup_runs = [
            entry for entry in client.runs
            if "HAS_PLANNED_DATE|HAS_COMPLETED_DATE" in entry["query"]
        ]
        self.assertEqual(cleanup_runs[0]["params"]["item_id"], "item_001")
        action_merges = [
            entry for entry in client.runs
            if "MERGE (a:ActionItem" in entry["query"]
        ]
        self.assertEqual(action_merges[0]["params"]["status"], "not_applicable")
        item_merges = [
            entry for entry in client.runs
            if "MERGE (i:MeetingItem" in entry["query"]
        ]
        self.assertEqual(item_merges[0]["params"]["status"], "not_applicable")

    def test_build_graph_persists_semantic_nodes_and_follow_up_links(self):
        meetings = [
            {
                "document_id": "doc_001",
                "meeting_id": "meeting_001",
                "meeting_name": "FDA review",
                "meeting_date": "2018-04-03",
            },
            {
                "document_id": "doc_002",
                "meeting_id": "meeting_002",
                "meeting_name": "FDA follow up",
                "meeting_date": "2018-04-10",
            },
        ]
        items = [
            {
                "item_id": "item_001",
                "meeting_id": "meeting_001",
                "item_no": "01",
                "content": "Conformity stem FDA submission has delay risk.",
                "owner": "Carol",
                "planned_date": "2018-04-20",
                "actual_completed_date": None,
                "tracking_result": "pending",
            },
            {
                "item_id": "item_002",
                "meeting_id": "meeting_002",
                "item_no": "01",
                "content": "Conformity stem FDA submission risk follow up decision approved.",
                "owner": "Carol",
                "planned_date": "2018-04-27",
                "actual_completed_date": "2018-04-26",
                "tracking_result": "completed",
            },
        ]
        client = _CapturingGraphClient()

        with patch("apps.graph.graph_builder.get_meeting_minutes_collection", return_value=_FakeCollection(meetings)), patch(
            "apps.graph.graph_builder.get_meeting_items_collection", return_value=_FakeCollection(items)
        ):
            summary = build_graph_from_mongo(client)

        self.assertGreaterEqual(summary["node_counts"]["ActionItem"], 2)
        self.assertGreaterEqual(summary["node_counts"]["Issue"], 1)
        self.assertGreaterEqual(summary["relationship_counts"]["TRACKS_ISSUE"], 2)
        self.assertGreaterEqual(summary["relationship_counts"]["FOLLOW_UP_OF"], 1)
        self.assertGreaterEqual(summary["relationship_counts"]["HAS_RISK"], 1)
        self.assertGreaterEqual(summary["relationship_counts"]["HAS_DECISION"], 1)

        queries = [entry["query"] for entry in client.runs]
        self.assertTrue(any("ActionItem" in query for query in queries))
        self.assertTrue(any("FOLLOW_UP_OF" in query for query in queries))

    def test_build_graph_persists_responsibility_changed_in_content(self):
        meeting = {
            "document_id": "doc_001",
            "meeting_id": "meeting_001",
            "meeting_name": "Responsibility update",
            "meeting_date": "2018-04-03",
        }
        item = {
            "item_id": "item_001",
            "meeting_id": "meeting_001",
            "item_no": "01",
            "content": "\u539f\u8ca0\u8cac\u4eba\u4f59\u67cf\u52f3\u6539\u70ba\u9673\u8056\u660c\u3001\u9673\u58eb\u6db5",
            "owner": "",
            "planned_date": None,
            "actual_completed_date": None,
            "tracking_result": "",
        }
        client = _CapturingGraphClient()

        with patch("apps.graph.graph_builder.get_meeting_minutes_collection", return_value=_FakeCollection([meeting])), patch(
            "apps.graph.graph_builder.get_meeting_items_collection", return_value=_FakeCollection([item])
        ):
            summary = build_graph_from_mongo(client)

        responsible_params = [
            entry["params"]
            for entry in client.runs
            if "RESPONSIBLE_BY" in entry["query"] and entry["params"].get("person_name")
        ]
        responsible_names = {params["person_name"] for params in responsible_params}
        self.assertIn("\u9673\u8056\u660c", responsible_names)
        self.assertIn("\u9673\u58eb\u6db5", responsible_names)
        self.assertGreaterEqual(summary["relationship_counts"]["RESPONSIBLE_BY"], 2)


class SemanticExtractorTestCase(SimpleTestCase):
    def test_extract_responsible_people_from_content_change_sentence(self):
        names = extract_responsible_people_from_text(
            "\u539f\u8ca0\u8cac\u4eba\u4f59\u67cf\u52f3\u6539\u70ba\u9673\u8056\u660c\u3001\u9673\u58eb\u6db5"
        )

        self.assertEqual(names, ["\u9673\u8056\u660c", "\u9673\u58eb\u6db5"])

    def test_extract_semantic_item_identifies_action_risk_decision_and_status(self):
        payload = extract_semantic_item(
            {
                "item_id": "item_001",
                "content": "Approved decision: Conformity stem FDA submission delay risk must be reviewed.",
                "owner": "Carol",
                "actual_completed_date": None,
                "tracking_result": "pending",
            }
        )

        self.assertEqual(payload["action"]["status"], "in_progress")
        self.assertIsNotNone(payload["risk"])
        self.assertIsNotNone(payload["decision"])
        self.assertIsNotNone(payload["issue"])

    def test_tracking_result_bare_complete_does_not_create_completed_status_without_actual_date(self):
        payload = extract_semantic_item(
            {
                "item_id": "item_001",
                "content": "請下次完成 FDA submission follow-up.",
                "owner": "Carol",
                "actual_completed_date": None,
                "tracking_result": "下次會議前完成",
            }
        )

        self.assertEqual(payload["action"]["status"], "pending")

    def test_tracking_result_high_confidence_completion_sets_completed_status(self):
        examples = (
            "新 竹 製 程 確 認完 成 ，詳 設 計 移 轉 會 議 投 影 片 ( 附 件一)",
            "確 認 已完 成 ，詳 設 計 移 轉 會 議 投 影片 ( 附件)",
        )

        for tracking_result in examples:
            payload = extract_semantic_item(
                {
                    "item_id": "item_001",
                    "content": "製程確認",
                    "owner": "Carol",
                    "actual_completed_date": None,
                    "tracking_result": tracking_result,
                }
            )

            self.assertEqual(payload["action"]["status"], "completed")
            self.assertEqual(payload["action"]["status_source"], "tracking_result")
            self.assertEqual(payload["action"]["status_confidence"], "high")

    def test_actual_completed_date_placeholder_does_not_create_completed_status(self):
        payload = extract_semantic_item(
            {
                "item_id": "item_001",
                "content": "FDA submission follow-up.",
                "owner": "Carol",
                "actual_completed_date": "--",
                "tracking_result": "",
            }
        )

        self.assertEqual(payload["action"]["status"], "pending")

    def test_not_applicable_tracking_result_does_not_create_completed_status(self):
        payload = extract_semantic_item(
            {
                "item_id": "item_001",
                "content": "可用性評估報告確認",
                "owner": "UR3",
                "planned_date": "--",
                "actual_completed_date": "--",
                "tracking_result": "不 適 用 ，詳 設 計 移 轉 會 議 投 影 片 ( 附 件)",
            }
        )

        self.assertEqual(payload["action"]["status"], "not_applicable")
        self.assertEqual(payload["action"]["status_source"], "tracking_result")
        self.assertEqual(payload["action"]["status_confidence"], "high")


class _FakeGraphClient:
    available = True

    def execute_read(self, callback, *args):
        return callback(_FakeTx(), *args)


class _FakeText2CypherClient:
    available = True

    def execute_read(self, callback, *args):
        return callback(_FakeText2CypherTx(), *args)


class _FailingText2CypherClient:
    available = True

    def execute_read(self, callback, *args):
        raise RuntimeError("Neo4j down")


class _FakeText2CypherTx:
    def run(self, cypher, **_params):
        if (
            "OPTIONAL MATCH (item)-[:RESPONSIBLE_BY]->(person:Person)" in cypher
            and "OPTIONAL MATCH (item)-[:HAS_PLANNED_DATE]->(planned_date:Date)" in cypher
        ):
            return [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Item detail review",
                    "meeting_date": "2017-12-01",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Complete FDA package.",
                    "people": ["Carol"],
                    "planned_dates": ["2017-12-15"],
                    "completed_dates": ["2018-04-13"],
                    "products": ["Conformity stem"],
                    "regulations": ["FDA"],
                    "keywords": ["label"],
                    "actions": ["Complete package"],
                    "decisions": ["Submit package"],
                    "risks": ["Timeline risk"],
                    "issues": ["FDA timeline"],
                }
            ]
        if "OPTIONAL MATCH (item)-[:RESPONSIBLE_BY]->(person:Person)" in cypher:
            return [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Item owner review",
                    "meeting_date": "2017-12-01",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Complete FDA package.",
                    "people": ["Carol"],
                }
            ]
        if "OPTIONAL MATCH (item)-[:HAS_PLANNED_DATE]->(planned_date:Date)" in cypher:
            return [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Item date review",
                    "meeting_date": "2017-12-01",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Complete FDA package.",
                    "planned_dates": ["2017-12-15"],
                    "completed_dates": ["2018-04-13"],
                }
            ]
        if "HAS_PLANNED_DATE|HAS_COMPLETED_DATE" in cypher:
            return [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "Date review",
                    "meeting_date": "2017-12-01",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Complete FDA package.",
                    "date_value": "2017-12-15",
                    "date_relation": "HAS_PLANNED_DATE",
                }
            ]
        if "MATCH (date:Date)" in cypher:
            return [{"date_value": "2017-12-15"}]
        if "MENTIONS_PRODUCT" in cypher and "meeting_count" in cypher:
            return [{"product": "Conformity stem", "meeting_count": 2, "item_count": 3}]
        if "MENTIONS_PRODUCT" in cypher:
            return [{"product": "Conformity stem", "mentions": 2}]
        if "MATCH (meeting:Meeting)" in cypher:
            return [{"meeting_id": "meeting_001"}]
        return []


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
    def run(self, cypher, **params):
        normalized_keyword = str(params.get("keyword") or "").strip().upper()
        normalized_keywords = [str(item or "").strip().upper() for item in params.get("keywords", [])]
        entity = str(params.get("entity") or "").strip().upper()
        relation = str(params.get("relation") or "").strip().upper()

        if "CO_OCCURS_WITH" in cypher:
            if normalized_keyword == "FDA":
                return [
                    {"keyword": "TFDA", "type": "abbreviation", "weight": 1.0, "count": 2},
                    {"keyword": "CFDA", "type": "abbreviation", "weight": 0.5, "count": 1},
                ]
            return []

        if "MATCH (item:MeetingItem)-[mention:MENTIONS]->(keyword:Keyword)" in cypher and "FDA" in normalized_keywords:
            return [
                {
                    "meeting_id": "meet_001",
                    "meeting_name": "FDA meeting",
                    "meeting_date": "2018-04-03",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "TFDA and FDA submission",
                    "matched_keyword": "TFDA",
                    "keyword_type": "abbreviation",
                    "matched_field": "content",
                    "keyword_score": 1.0,
                    "keyword_method": "regex_abbreviation",
                }
            ]

        if "QUERY_MEETING_ITEMS_BY_QUERY" in cypher:
            return []

        if "MATCH (candidate:Meeting)" in cypher and "best_score" in cypher:
            return [
                {
                    "meeting_id": "meet_items",
                    "meeting_name": "Owner review meeting",
                    "meeting_date": "2018-04-03",
                    "item_id": f"item_{index:03d}",
                    "item_no": f"{index:02d}",
                    "content": f"Meeting item {index}",
                    "matched_entity": "Owner review meeting",
                    "matched_relation": "HAS_ITEM",
                    "matched_field": "meeting_items",
                }
                for index in range(1, 6)
            ]

        if "MATCH (issue:Issue)<-[:TRACKS_ISSUE]-(item:MeetingItem)" in cypher:
            if normalized_keyword and normalized_keyword not in {"FDA", "CONFORMITY STEM"}:
                return []
            return [
                {
                    "meeting_id": "meet_006",
                    "meeting_name": "Initial issue meeting",
                    "meeting_date": "2018-04-08",
                    "item_id": "item_006",
                    "item_no": "06",
                    "content": "FDA timeline needs follow-up.",
                    "issue_id": "issue_fda",
                    "issue_title": "FDA timeline",
                    "issue_signature": "fda_timeline",
                    "matched_entity": "FDA timeline",
                    "matched_relation": "TRACKS_ISSUE",
                    "matched_node_id": "issue_fda",
                    "matched_field": "issue_timeline",
                    "previous_item_id": None,
                    "next_item_id": "item_007",
                    "next_meeting_id": "meet_007",
                },
                {
                    "meeting_id": "meet_007",
                    "meeting_name": "Follow up meeting",
                    "meeting_date": "2018-04-09",
                    "item_id": "item_007",
                    "item_no": "07",
                    "content": "Follow up FDA action.",
                    "issue_id": "issue_fda",
                    "issue_title": "FDA timeline",
                    "issue_signature": "fda_timeline",
                    "matched_entity": "FDA timeline",
                    "matched_relation": "TRACKS_ISSUE",
                    "matched_node_id": "issue_fda",
                    "matched_field": "issue_timeline",
                    "previous_item_id": "item_006",
                    "previous_meeting_id": "meet_006",
                    "next_item_id": None,
                },
            ]

        if "OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)" in cypher:
            if normalized_keyword and normalized_keyword not in {"FDA", "CONFORMITY STEM"}:
                return []
            return [
                {
                    "meeting_id": "meet_006",
                    "meeting_name": "Composite meeting",
                    "meeting_date": "2018-04-08",
                    "item_id": "item_006",
                    "item_no": "06",
                    "content": "Carol handles FDA Conformity stem open action.",
                    "matched_entity": "Carol handles FDA Conformity stem open action.",
                    "matched_relation": "HAS_ACTION",
                    "matched_node_id": "action_item_006",
                    "matched_field": params.get("target", "action_items"),
                    "semantic_status": "pending",
                    "owner_names": ["Carol"],
                    "assignee_names": ["Carol"],
                    "unit_names": ["UR3"],
                    "product_names": ["Conformity stem"],
                    "action_product_names": ["Conformity stem"],
                    "regulation_names": ["FDA"],
                    "action_regulation_names": ["FDA"],
                    "keyword_names": ["FDA"],
                }
            ]

        if "FOLLOW_UP_OF" in cypher:
            return [
                {
                    "meeting_id": "meet_007",
                    "meeting_name": "Follow up meeting",
                    "meeting_date": "2018-04-09",
                    "item_id": "item_007",
                    "item_no": "07",
                    "content": "Follow up FDA action.",
                    "matched_entity": "item_006",
                    "matched_relation": "FOLLOW_UP_OF",
                    "matched_node_id": "item_006",
                    "matched_field": "follow_up",
                    "previous_meeting_id": "meet_006",
                }
            ]

        if "RESPONSIBLE_BY" in cypher:
            if not entity or "CAROL" in entity:
                return [
                    {
                        "meeting_id": "meet_001",
                        "meeting_name": "Owner meeting",
                        "meeting_date": "2018-04-03",
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "Prepare label submission.",
                        "matched_entity": "Carol",
                        "matched_relation": "RESPONSIBLE_BY",
                        "matched_field": "owner",
                    }
                ]
            return []

        if "type(relation) = $relation" in cypher and relation in {"ATTENDED_BY", "CHAIRED_BY", "RECORDED_BY"}:
            return [
                {
                    "meeting_id": "meet_001",
                    "meeting_name": "Role meeting",
                    "meeting_date": "2018-04-03",
                    "item_id": "item_001",
                    "item_no": "01",
                    "content": "Role related item.",
                    "matched_entity": "Carol",
                    "matched_relation": relation,
                    "matched_field": relation.lower(),
                }
            ]

        if "BELONGS_TO_UNIT" in cypher:
            return [
                {
                    "meeting_id": "meet_002",
                    "meeting_name": "Unit meeting",
                    "meeting_date": "2018-04-04",
                    "item_id": "item_002",
                    "item_no": "02",
                    "content": "Unit related item.",
                    "matched_entity": "UR3",
                    "matched_relation": "BELONGS_TO_UNIT",
                    "matched_field": "responsible_unit",
                }
            ]

        if "HAS_PLANNED_DATE" in cypher or "HAS_COMPLETED_DATE" in cypher:
            return [
                {
                    "meeting_id": "meet_003",
                    "meeting_name": "Date meeting",
                    "meeting_date": "2018-04-05",
                    "item_id": "item_003",
                    "item_no": "03",
                    "content": "Date related item.",
                    "matched_entity": "2018-04-20",
                    "matched_relation": relation,
                    "matched_field": "planned_date" if relation == "HAS_PLANNED_DATE" else "actual_completed_date",
                }
            ]

        if "MENTIONS_PRODUCT" in cypher:
            return [
                {
                    "meeting_id": "meet_004",
                    "meeting_name": "Product meeting",
                    "meeting_date": "2018-04-06",
                    "item_id": "item_004",
                    "item_no": "04",
                    "content": "Product related item.",
                    "matched_entity": "Conformity stem",
                    "matched_relation": "MENTIONS_PRODUCT",
                    "matched_field": "content",
                }
            ]

        if "MENTIONS_REGULATION" in cypher:
            return [
                {
                    "meeting_id": "meet_005",
                    "meeting_name": "Regulation meeting",
                    "meeting_date": "2018-04-07",
                    "item_id": "item_005",
                    "item_no": "05",
                    "content": "Regulation related item.",
                    "matched_entity": "FDA",
                    "matched_relation": "MENTIONS_REGULATION",
                    "matched_field": "content",
                }
            ]
        return []


class GraphSearchTestCase(SimpleTestCase):
    def test_composite_query_uses_cypher_string_literals_for_status_filters(self):
        query = cq.QUERY_COMPOSITE_GRAPH_SEARCH

        for literal in ("action_items", "completed", "not_applicable", "pending"):
            self.assertIn(f"'{literal}'", query)
            self.assertNotIn(f'"{literal}"', query)
        self.assertIn(
            "OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)\n"
            "WITH meeting, item, action, decision, risk, issue\n"
            "WHERE",
            query,
        )
        self.assertIn("$target <> 'action_items' OR action IS NOT NULL", query)
        self.assertIn("$status = 'completed'", query)
        self.assertIn("$status = 'not_applicable'", query)

    def test_query_planner_parses_composite_constraints(self):
        payload = analyze_graph_query_plan(
            "Carol is responsible for FDA not completed Conformity stem items",
            llm_client=lambda _question: (
                '{"target":"action_items","constraints":{"person_name":"Carol",'
                '"product_name":"Conformity stem","regulation_name":"FDA","status":"not_completed"},'
                '"include_followups":true}'
            ),
        )

        self.assertEqual(payload["target"], "action_items")
        self.assertEqual(payload["constraints"]["person_name"], "Carol")
        self.assertEqual(payload["constraints"]["regulation_name"], "FDA")
        self.assertEqual(payload["constraints"]["status"], "not_completed")
        self.assertTrue(payload["include_followups"])

    def test_heuristic_query_plan_targets_risks(self):
        payload = heuristic_query_plan("FDA open risk items")

        self.assertEqual(payload["target"], "risks")
        self.assertEqual(payload["constraints"]["status"], "not_completed")
        self.assertEqual(payload["constraints"]["regulation_name"].upper(), "FDA")

    def test_heuristic_query_plan_does_not_treat_due_questions_as_completed(self):
        payload = heuristic_query_plan("2017 年 12 月 15 日要完成哪些事項")

        self.assertEqual(payload["constraints"]["status"], "")

    def test_analyze_query_plan_uses_deterministic_plan_for_chinese_status_items(self):
        payload = analyze_graph_query_plan(
            "已完成的事項有哪些",
            llm_client=lambda _question: self.fail("Chinese status item query should not require LLM"),
        )

        self.assertEqual(payload["target"], "action_items")
        self.assertEqual(payload["constraints"]["status"], "completed")
        self.assertEqual(payload["constraints"]["keyword"], "")

    @override_settings(GRAPH_QUERY_PLANNER_MODE="llm_first")
    def test_analyze_query_plan_can_prioritize_llm_for_chinese_status_items(self):
        payload = analyze_graph_query_plan(
            "已完成的事項有哪些",
            llm_client=lambda _question: (
                '{"target":"decisions","constraints":{"person_name":"","unit_name":"","product_name":"",'
                '"regulation_name":"","status":"completed","keyword":"測試"},"include_followups":false}'
            ),
        )

        self.assertEqual(payload["target"], "decisions")
        self.assertEqual(payload["constraints"]["status"], "completed")
        self.assertEqual(payload["constraints"]["keyword"], "測試")

    @override_settings(GRAPH_QUERY_PLANNER_MODE="deterministic_only")
    def test_analyze_query_plan_can_disable_llm(self):
        payload = analyze_graph_query_plan(
            "Carol is responsible for FDA not completed Conformity stem items",
            llm_client=lambda _question: self.fail("LLM should not run in deterministic_only mode"),
        )

        self.assertEqual(payload["target"], "action_items")
        self.assertEqual(payload["constraints"]["regulation_name"], "FDA")
        self.assertEqual(payload["constraints"]["status"], "not_completed")

    def test_analyze_query_plan_keeps_unknown_decision_subject_as_keyword_constraint(self):
        payload = analyze_graph_query_plan(
            "晚餐的決議是否已完成？",
            llm_client=lambda _question: self.fail("Chinese decision status query should not require LLM"),
        )

        self.assertEqual(payload["target"], "decisions")
        self.assertEqual(payload["constraints"]["status"], "completed")
        self.assertEqual(payload["constraints"]["keyword"], "晚餐")

    def test_analyze_query_plan_uses_deterministic_plan_for_chinese_mixed_constraints(self):
        payload = analyze_graph_query_plan(
            "陳聖昌 FDA Conformity stem 未完成事項",
            llm_client=lambda _question: self.fail("Chinese mixed constraint query should not require LLM"),
        )

        self.assertEqual(payload["target"], "action_items")
        self.assertEqual(payload["constraints"]["person_name"], "陳聖昌")
        self.assertEqual(payload["constraints"]["regulation_name"], "FDA")
        self.assertEqual(payload["constraints"]["product_name"], "Conformity stem")
        self.assertEqual(payload["constraints"]["status"], "not_completed")

    def test_analyze_query_plan_uses_deterministic_plan_for_chinese_semantic_targets(self):
        cases = [
            ("FDA 相關風險整理", "risks"),
            ("有哪些決議", "decisions"),
            ("跨會議追蹤整理", "issues"),
        ]

        for question, target in cases:
            with self.subTest(question=question):
                payload = analyze_graph_query_plan(
                    question,
                    llm_client=lambda _question: self.fail("Chinese semantic summary should not require LLM"),
                )
                self.assertEqual(payload["target"], target)

    def test_analyze_graph_intent_parses_llm_json(self):
        payload = analyze_graph_intent(
            "What is Carol responsible for?",
            llm_client=lambda _question: '{"intent":"person_responsibility","entities":{"person_name":"Carol"}}',
        )

        self.assertEqual(payload["intent"], "person_responsibility")
        self.assertEqual(payload["entities"]["person_name"], "Carol")
        self.assertEqual(payload["warnings"], [])

    def test_analyze_graph_intent_returns_warning_for_invalid_json(self):
        payload = analyze_graph_intent("What is Carol responsible for?", llm_client=lambda _question: "not json")

        self.assertEqual(payload["intent"], "person_responsibility")
        self.assertEqual(payload["entities"]["person_name"], "Carol")
        self.assertEqual(payload["warnings"], [])

    def test_analyze_graph_intent_uses_deterministic_date_intent(self):
        payload = analyze_graph_intent(
            "2017 年 12 月 15 日要完成哪些事項",
            llm_client=lambda _question: self.fail("date intent should not require LLM"),
        )

        self.assertEqual(payload["intent"], "planned_date")
        self.assertEqual(payload["entities"]["date_value"], "2017-12-15")
        self.assertEqual(payload["warnings"], [])

    def test_analyze_graph_intent_uses_deterministic_person_relation_intents(self):
        cases = [
            ("陳聖昌出席哪些會議", "person_attendance"),
            ("陳聖昌主持哪些會議", "meeting_chair"),
            ("陳聖昌記錄哪些會議", "meeting_recorder"),
            ("陳聖昌負責哪些項目", "person_responsibility"),
        ]

        for question, intent in cases:
            with self.subTest(question=question):
                payload = analyze_graph_intent(
                    question,
                    llm_client=lambda _query: self.fail("deterministic person intent should not require LLM"),
                )
                self.assertEqual(payload["intent"], intent)
                self.assertEqual(payload["entities"]["person_name"], "陳聖昌")

    def test_heuristic_query_plan_extracts_mixed_constraints(self):
        payload = heuristic_query_plan("陳聖昌 FDA Conformity stem 未完成事項")

        self.assertEqual(payload["target"], "action_items")
        self.assertEqual(payload["constraints"]["person_name"], "陳聖昌")
        self.assertEqual(payload["constraints"]["regulation_name"].upper(), "FDA")
        self.assertEqual(payload["constraints"]["product_name"], "Conformity stem")
        self.assertEqual(payload["constraints"]["status"], "not_completed")

    def test_fetch_related_keywords_is_case_insensitive(self):
        payload = fetch_related_keywords(_FakeGraphClient(), "fda", limit=10)

        self.assertEqual(payload[0]["keyword"], "TFDA")
        self.assertEqual(payload[1]["keyword"], "CFDA")

    def test_search_graph_expands_keywords_for_lowercase_query(self):
        payload = search_graph(_FakeGraphClient(), "fda", limit=10)

        self.assertEqual(payload["expanded_keywords"], ["TFDA", "CFDA"])
        self.assertEqual(payload["results"][0]["matched_keyword"], "TFDA")
        self.assertEqual(payload["results"][0]["keyword_method"], "regex_abbreviation")
        self.assertGreater(payload["results"][0]["graph_score"], 0)

    def test_search_graph_uses_responsible_by_for_person_intent(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Carol",
            limit=10,
            intent_analyzer=lambda _query: {
                "intent": "person_responsibility",
                "entities": {"person_name": "Carol"},
                "warnings": [],
            },
        )

        self.assertEqual(payload["intent"], "person_responsibility")
        self.assertEqual(payload["results"][0]["matched_relation"], "RESPONSIBLE_BY")
        self.assertEqual(payload["results"][0]["matched_entity"], "Carol")

    def test_search_graph_can_return_all_responsible_items_without_person_name(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Who is responsible for each item?",
            limit=10,
            intent_analyzer=lambda _query: {
                "intent": "person_responsibility",
                "entities": {"person_name": ""},
                "warnings": [],
            },
        )

        self.assertEqual(payload["results"][0]["matched_relation"], "RESPONSIBLE_BY")

    def test_search_graph_uses_ascii_responsibility_token_as_exact_person_constraint(self):
        payload = search_graph(
            _FakeGraphClient(),
            "gdfgdfh負責哪些項目",
            limit=10,
            intent_analyzer=analyze_graph_intent,
        )

        self.assertEqual(payload["intent"], "person_responsibility")
        self.assertEqual(payload["intent_entities"]["person_name"], "gdfgdfh")
        self.assertEqual(payload["results"], [])

    def test_search_graph_supports_core_relation_intents(self):
        cases = [
            ("person_attendance", {"person_name": "Carol"}, "ATTENDED_BY"),
            ("meeting_chair", {"person_name": "Carol"}, "CHAIRED_BY"),
            ("meeting_recorder", {"person_name": "Carol"}, "RECORDED_BY"),
            ("unit_meetings", {"unit_name": "UR3"}, "BELONGS_TO_UNIT"),
            ("planned_date", {"date_value": "2018-04"}, "HAS_PLANNED_DATE"),
            ("completed_date", {"date_value": "2018-04"}, "HAS_COMPLETED_DATE"),
            ("product_related", {"product_name": "stem"}, "MENTIONS_PRODUCT"),
            ("regulation_related", {"regulation_name": "FDA"}, "MENTIONS_REGULATION"),
        ]

        for intent, entities, relation in cases:
            with self.subTest(intent=intent):
                payload = search_graph(
                    _FakeGraphClient(),
                    "query",
                    limit=10,
                    intent_analyzer=lambda _query, intent=intent, entities=entities: {
                        "intent": intent,
                        "entities": entities,
                        "warnings": [],
                    },
                )

                self.assertEqual(payload["results"][0]["matched_relation"], relation)

    def test_search_graph_returns_date_relation_before_composite_status_results(self):
        payload = search_graph(
            _FakeGraphClient(),
            "2018-04-13 實際完成哪些事項",
            limit=10,
            intent_analyzer=lambda _query: {
                "intent": "completed_date",
                "entities": {"date_value": "2018-04-13"},
                "warnings": [],
            },
            query_planner=lambda _query: {
                "target": "action_items",
                "constraints": {"status": "completed"},
                "include_followups": False,
                "warnings": [],
            },
        )

        self.assertEqual(payload["intent"], "completed_date")
        self.assertEqual(payload["results"][0]["matched_relation"], "HAS_COMPLETED_DATE")
        self.assertTrue(all(result["retrieval_mode"] == "relation" for result in payload["results"]))

    def test_search_graph_uses_composite_query_plan_for_mixed_constraints(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Carol FDA not completed action items",
            limit=10,
            query_planner=lambda _query: {
                "target": "action_items",
                "constraints": {
                    "person_name": "Carol",
                    "product_name": "Conformity stem",
                    "regulation_name": "FDA",
                    "status": "not_completed",
                },
                "include_followups": True,
                "warnings": [],
            },
        )

        relations = {result["matched_relation"] for result in payload["results"]}
        self.assertIn("HAS_ACTION", relations)
        self.assertIn("FOLLOW_UP_OF", relations)
        self.assertEqual(payload["query_plan"]["target"], "action_items")
        action_result = next(result for result in payload["results"] if result["matched_relation"] == "HAS_ACTION")
        evidence_relations = action_result["evidence_relations"]
        evidence_labels = {relation["relation"] for relation in evidence_relations}
        self.assertIn("RESPONSIBLE_BY", evidence_labels)
        self.assertIn("MENTIONS_REGULATION", evidence_labels)
        self.assertIn("MENTIONS_PRODUCT", evidence_labels)

    def test_search_graph_requires_keyword_match_for_unknown_decision_subject(self):
        payload = search_graph(
            _FakeGraphClient(),
            "晚餐的決議是否已完成？",
            limit=10,
            query_planner=analyze_graph_query_plan,
        )

        self.assertEqual(payload["query_plan"]["target"], "decisions")
        self.assertEqual(payload["query_plan"]["constraints"]["keyword"], "晚餐")
        self.assertEqual(payload["results"], [])

    def test_search_graph_returns_issue_timeline_for_follow_up_mode(self):
        payload = search_graph(
            _FakeGraphClient(),
            "FDA 相關追蹤事項",
            limit=10,
            retrieval_modes=("follow_up",),
        )

        self.assertEqual(payload["intent"], "follow_up_tracking")
        self.assertEqual(payload["query_plan"]["target"], "issues")
        self.assertEqual([result["sequence_no"] for result in payload["results"]], [1, 2])
        self.assertTrue(all(result["matched_relation"] == "TRACKS_ISSUE" for result in payload["results"]))
        self.assertTrue(all(result["retrieval_mode"] == "follow_up" for result in payload["results"]))
        evidence_labels = {relation["relation"] for relation in payload["results"][0]["evidence_relations"]}
        self.assertIn("TRACKS_ISSUE", evidence_labels)
        self.assertIn("FOLLOW_UP_OF", evidence_labels)

    def test_search_graph_uses_has_item_for_meeting_item_list_questions(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Which items are included in Owner review meeting?",
            limit=10,
        )

        self.assertEqual(len(payload["results"]), 5)
        self.assertTrue(all(result["matched_relation"] == "HAS_ITEM" for result in payload["results"]))
        self.assertEqual(payload["results"][0]["match_type"], "meeting_items")
        self.assertEqual(payload["results"][0]["retrieval_mode"], "structural")

    def test_search_graph_can_limit_retrieval_modes(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Owner review meeting 的討論事項",
            limit=10,
            retrieval_modes=("structural",),
        )

        self.assertEqual(payload["retrieval_modes"], ["structural"])
        self.assertEqual(len(payload["results"]), 5)
        self.assertTrue(all(result["retrieval_mode"] == "structural" for result in payload["results"]))

    def test_meeting_query_terms_keep_meeting_identifiers(self):
        self.assertEqual(meeting_query_terms("P1812 會議包含哪些項目"), ["P1812"])
        self.assertEqual(meeting_query_terms("P1812 會議的討論事項"), ["P1812"])

    def test_search_graph_does_not_let_generic_action_plan_override_responsibility_intent(self):
        payload = search_graph(
            _FakeGraphClient(),
            "Who is responsible for each item?",
            limit=10,
            intent_analyzer=lambda _query: {
                "intent": "person_responsibility",
                "entities": {"person_name": ""},
                "warnings": [],
            },
            query_planner=lambda _query: {
                "target": "action_items",
                "constraints": {},
                "include_followups": False,
                "warnings": [],
            },
        )

        self.assertEqual(payload["results"][0]["matched_relation"], "RESPONSIBLE_BY")


class Text2CypherTestCase(SimpleTestCase):
    def test_text2cypher_timeout_setting_has_exploration_default(self):
        self.assertGreaterEqual(settings.TEXT2CYPHER_LLM_TIMEOUT, 45)
        self.assertGreaterEqual(settings.TEXT2CYPHER_MAX_LIMIT, 1)

    def test_validate_cypher_blocks_write_operations(self):
        payload = validate_cypher("MATCH (m:Meeting) DELETE m RETURN m")

        self.assertFalse(payload["is_valid"])
        self.assertTrue(any("DELETE" in warning for warning in payload["warnings"]))

    def test_validate_cypher_blocks_unknown_schema(self):
        payload = validate_cypher("MATCH (x:Secret)-[:HACKS]->(m:Meeting) RETURN x LIMIT 5")

        self.assertFalse(payload["is_valid"])
        self.assertTrue(any("Unsupported labels" in warning for warning in payload["warnings"]))
        self.assertTrue(any("Unsupported relationships" in warning for warning in payload["warnings"]))

    def test_explore_text2cypher_executes_safe_read_query(self):
        client = _FakeText2CypherClient()
        payload = explore_text2cypher(
            client,
            "哪些產品跨最多會議被討論？",
            limit=5,
            llm_client=lambda _question, _limit: self.fail("template example should avoid LLM"),
        )

        self.assertFalse(payload["blocked"])
        self.assertEqual(payload["generated_by"], "example_template")
        self.assertIn("LIMIT 5", payload["cypher"])
        self.assertEqual(payload["rows"], [{"product": "Conformity stem", "meeting_count": 2, "item_count": 3}])
        self.assertEqual(payload["graph"]["nodes"][0]["type"], "Product")

    def test_explore_text2cypher_still_uses_llm_for_unknown_exploration(self):
        payload = explore_text2cypher(
            _FakeText2CypherClient(),
            "列出最近的會議",
            limit=5,
            llm_client=lambda _question, _limit: (
                '{"cypher":"MATCH (meeting:Meeting) RETURN meeting.meeting_id AS meeting_id '
                'ORDER BY meeting.meeting_date DESC"}'
            ),
        )

        self.assertFalse(payload["blocked"])
        self.assertEqual(payload["generated_by"], "llm")
        self.assertIn("LIMIT 5", payload["cypher"])

    def test_text2cypher_prompt_includes_schema_and_few_shot_examples(self):
        prompt = build_text2cypher_prompt("哪些人負責最多事項？", 10)

        self.assertIn("Core graph patterns", prompt)
        self.assertIn("(Meeting)-[:HAS_ITEM]->(MeetingItem)", prompt)
        self.assertIn("MATCH path = (...)", prompt)
        self.assertIn("RETURN path plus scalar fields", prompt)
        self.assertIn("Few-shot examples", prompt)
        self.assertIn("哪些產品跨最多會議被討論", prompt)

    def test_template_cypher_covers_common_exploration_questions(self):
        cases = [
            "哪些產品跨最多會議被討論？",
            "哪些人負責最多事項？",
            "哪些會議同時提到 FDA 和 TFDA？",
            "哪些 issue 沒有 follow-up？",
            "哪些產品和法規最常一起出現？",
            "哪些人和 Conformity stem 最常一起出現？",
        ]

        for question in cases:
            with self.subTest(question=question):
                self.assertTrue(template_cypher_for_question(question))

    def test_build_text2cypher_graph_projects_rows_to_nodes_and_edges(self):
        graph = build_text2cypher_graph(
            [
                {
                    "meeting_id": "meeting_001",
                    "meeting_name": "FDA meeting",
                    "item_id": "item_001",
                    "item_no": "01",
                    "product": "Conformity stem",
                    "regulation": "FDA",
                    "person": "Carol",
                }
            ]
        )

        node_types = {node["type"] for node in graph["nodes"]}
        edge_labels = {edge["label"] for edge in graph["edges"]}
        self.assertIn("Meeting", node_types)
        self.assertIn("MeetingItem", node_types)
        self.assertIn("Product", node_types)
        self.assertIn("Regulation", node_types)
        self.assertIn("Person", node_types)
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("MENTIONS_PRODUCT", edge_labels)
        self.assertIn("MENTIONS_REGULATION", edge_labels)
        self.assertIn("RESPONSIBLE_BY", edge_labels)

    def test_build_text2cypher_graph_projects_serialized_neo4j_nodes(self):
        graph = build_text2cypher_graph(
            [
                {
                    "meeting": {
                        "_labels": ["Meeting"],
                        "meeting_id": "meeting_001",
                        "meeting_name": "Date review",
                    },
                    "item": {
                        "_labels": ["MeetingItem"],
                        "item_id": "item_001",
                        "item_no": "01",
                        "content": "Complete FDA package.",
                    },
                    "date": {"_labels": ["Date"], "date_value": "2017-12-15"},
                    "date_relation": "HAS_PLANNED_DATE",
                }
            ]
        )

        edge_labels = {edge["label"] for edge in graph["edges"]}
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertIn("Meeting", node_types)
        self.assertIn("MeetingItem", node_types)
        self.assertIn("Date", node_types)
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("HAS_PLANNED_DATE", edge_labels)

    def test_build_text2cypher_graph_projects_serialized_paths(self):
        graph = build_text2cypher_graph(
            [
                {
                    "path": {
                        "_type": "Path",
                        "nodes": [
                            {
                                "_type": "Node",
                                "_labels": ["Meeting"],
                                "meeting_id": "meeting_001",
                                "meeting_name": "Date review",
                            },
                            {
                                "_type": "Node",
                                "_labels": ["MeetingItem"],
                                "item_id": "item_001",
                                "item_no": "01",
                                "content": "Complete FDA package.",
                            },
                            {
                                "_type": "Node",
                                "_labels": ["Date"],
                                "date_value": "2017-12-15",
                            },
                        ],
                        "relationships": [
                            {
                                "_type": "Relationship",
                                "_relationship_type": "HAS_ITEM",
                                "_source_index": 0,
                                "_target_index": 1,
                            },
                            {
                                "_type": "Relationship",
                                "_relationship_type": "HAS_PLANNED_DATE",
                                "_source_index": 1,
                                "_target_index": 2,
                            },
                        ],
                    },
                    "meeting_id": "meeting_001",
                    "item_id": "item_001",
                    "date_value": "2017-12-15",
                }
            ]
        )

        edge_labels = {edge["label"] for edge in graph["edges"]}
        node_ids = {node["id"] for node in graph["nodes"]}
        self.assertIn("Meeting:meeting_001", node_ids)
        self.assertIn("MeetingItem:item_001", node_ids)
        self.assertIn("Date:2017-12-15", node_ids)
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("HAS_PLANNED_DATE", edge_labels)
        self.assertEqual(graph["summary"]["path_count"], 1)

    def test_explore_text2cypher_does_not_expand_isolated_nodes_by_default(self):
        payload = explore_text2cypher(
            _FakeText2CypherClient(),
            "list dates",
            limit=5,
            llm_client=lambda _question, _limit: (
                '{"cypher":"MATCH (date:Date) RETURN date.date_value AS date_value"}'
            ),
        )

        edge_labels = {edge["label"] for edge in payload["graph"]["edges"]}
        node_types = {node["type"] for node in payload["graph"]["nodes"]}
        self.assertFalse(payload["blocked"])
        self.assertIn("Date", node_types)
        self.assertNotIn("HAS_ITEM", edge_labels)
        self.assertTrue(any("without paths" in warning for warning in payload["warnings"]))

    @override_settings(TEXT2CYPHER_ENABLE_NODE_EXPANSION=True)
    def test_explore_text2cypher_can_expand_isolated_date_nodes_when_enabled(self):
        payload = explore_text2cypher(
            _FakeText2CypherClient(),
            "list dates",
            limit=5,
            llm_client=lambda _question, _limit: (
                '{"cypher":"MATCH (date:Date) RETURN date.date_value AS date_value"}'
            ),
        )

        edge_labels = {edge["label"] for edge in payload["graph"]["edges"]}
        node_types = {node["type"] for node in payload["graph"]["nodes"]}
        self.assertFalse(payload["blocked"])
        self.assertIn("Meeting", node_types)
        self.assertIn("MeetingItem", node_types)
        self.assertIn("Date", node_types)
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("HAS_PLANNED_DATE", edge_labels)
        self.assertEqual(payload["graph"]["summary"]["expansion"], "deterministic_node_expansion")

    def test_text2cypher_expansion_uses_exact_matching_to_avoid_unrelated_graph(self):
        date_query = text2cypher_expansion_query("Date")
        item_query = text2cypher_expansion_query("MeetingItem")

        self.assertIn("date.date_value, '') = $value", date_query)
        self.assertIn("item.item_id, '')) = $value_upper", item_query)
        self.assertNotIn("CONTAINS $value", date_query)
        self.assertNotIn("coalesce(item.item_no", item_query)
        self.assertNotIn("coalesce(item.content", item_query)

    def test_expand_graph_node_returns_manual_expansion_graph(self):
        payload = expand_graph_node(_FakeText2CypherClient(), "Date:2017-12-15", limit=5)

        edge_labels = {edge["label"] for edge in payload["graph"]["edges"]}
        self.assertEqual(payload["node_type"], "Date")
        self.assertEqual(payload["graph"]["summary"]["projection"], "manual_node_expansion")
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("HAS_PLANNED_DATE", edge_labels)

    def test_expand_meeting_item_can_expand_owner_and_dates_separately(self):
        owner_payload = expand_graph_node(
            _FakeText2CypherClient(),
            "MeetingItem:item_001",
            limit=5,
            relation_scope="owner",
        )
        date_payload = expand_graph_node(
            _FakeText2CypherClient(),
            "MeetingItem:item_001",
            limit=5,
            relation_scope="dates",
        )

        owner_edge_labels = {edge["label"] for edge in owner_payload["graph"]["edges"]}
        date_edge_labels = {edge["label"] for edge in date_payload["graph"]["edges"]}
        owner_node_types = {node["type"] for node in owner_payload["graph"]["nodes"]}
        date_node_types = {node["type"] for node in date_payload["graph"]["nodes"]}
        self.assertEqual(owner_payload["node_type"], "MeetingItem")
        self.assertEqual(owner_payload["relation_scope"], "owner")
        self.assertEqual(date_payload["relation_scope"], "dates")
        self.assertIn("Meeting", owner_node_types)
        self.assertIn("Person", owner_node_types)
        self.assertIn("Date", date_node_types)
        self.assertIn("HAS_ITEM", owner_edge_labels)
        self.assertIn("RESPONSIBLE_BY", owner_edge_labels)
        self.assertIn("HAS_PLANNED_DATE", date_edge_labels)
        self.assertIn("HAS_COMPLETED_DATE", date_edge_labels)
        self.assertNotIn("HAS_PLANNED_DATE", owner_edge_labels)
        self.assertNotIn("RESPONSIBLE_BY", date_edge_labels)

    def test_expand_meeting_item_can_expand_all_relations_when_requested(self):
        payload = expand_graph_node(
            _FakeText2CypherClient(),
            "MeetingItem:item_001",
            limit=5,
            relation_scope="all",
        )

        edge_labels = {edge["label"] for edge in payload["graph"]["edges"]}
        node_types = {node["type"] for node in payload["graph"]["nodes"]}
        self.assertEqual(payload["relation_scope"], "all")
        self.assertIn("Meeting", node_types)
        self.assertIn("Person", node_types)
        self.assertIn("Date", node_types)
        self.assertIn("Product", node_types)
        self.assertIn("Regulation", node_types)
        self.assertIn("HAS_ITEM", edge_labels)
        self.assertIn("RESPONSIBLE_BY", edge_labels)
        self.assertIn("HAS_PLANNED_DATE", edge_labels)
        self.assertIn("HAS_COMPLETED_DATE", edge_labels)
        self.assertIn("MENTIONS_PRODUCT", edge_labels)
        self.assertIn("MENTIONS_REGULATION", edge_labels)

    def test_expand_graph_node_returns_warning_on_query_failure(self):
        payload = expand_graph_node(_FailingText2CypherClient(), "Date:2017-12-15", limit=5)

        self.assertEqual(payload["graph"]["nodes"], [])
        self.assertTrue(any("Unable to expand graph node" in warning for warning in payload["warnings"]))

    def test_explore_text2cypher_returns_blocked_payload_for_unsafe_query(self):
        payload = explore_text2cypher(
            _FakeText2CypherClient(),
            "刪除資料",
            limit=5,
            llm_client=lambda _question, _limit: '{"cypher":"MATCH (m:Meeting) DETACH DELETE m"}',
        )

        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["rows"], [])
        self.assertTrue(payload["warnings"])

