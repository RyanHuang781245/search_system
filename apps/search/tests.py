from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.urls import reverse
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APISimpleTestCase

from .ranking import has_task_intent, score_item


class SearchRankingTestCase(SimpleTestCase):
    def test_task_score_only_applies_to_task_intent_queries(self):
        item = {
            "content": "FDA submission discussion",
            "owner": "Alice",
            "planned_date": "2018-04-20",
            "actual_completed_date": None,
            "tracking_result": None,
        }

        topic_score = score_item(item, "FDA")
        task_score = score_item(item, "未完成追蹤")

        self.assertFalse(has_task_intent("FDA"))
        self.assertTrue(has_task_intent("未完成追蹤"))
        self.assertEqual(topic_score["task_score"], 0.0)
        self.assertEqual(task_score["task_score"], 7.0)


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
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append({"keys": keys, **kwargs})
        return kwargs.get("name", "idx")

    def insert_one(self, document):
        self.documents.append(dict(document))

    def insert_many(self, documents):
        for document in documents:
            self.insert_one(document)

    def find(self, query=None, projection=None):
        results = [self._project(document, projection) for document in self.documents if self._matches(document, query or {})]
        return FakeCursor(results)

    def find_one(self, query, projection=None):
        for document in self.documents:
            if self._matches(document, query):
                return self._project(document, projection)
        return None

    def count_documents(self, query):
        return len([document for document in self.documents if self._matches(document, query)])

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
            if document.get(key) != expected:
                return False
        return True


class SearchAPITestCase(APISimpleTestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.meeting_minutes_collection = FakeMongoCollection()
        self.meeting_items_collection = FakeMongoCollection()
        self.search_logs_collection = FakeMongoCollection()
        self.search_click_logs_collection = FakeMongoCollection()

        self.patchers = [
            patch("apps.search.services.get_meeting_minutes_collection", return_value=self.meeting_minutes_collection),
            patch("apps.search.services.get_meeting_items_collection", return_value=self.meeting_items_collection),
            patch("apps.search.services.get_search_logs_collection", return_value=self.search_logs_collection),
            patch("apps.search.services.get_search_click_logs_collection", return_value=self.search_click_logs_collection),
            patch("apps.search.services.ensure_indexes", return_value=None),
            patch("apps.search.feedback.get_search_click_logs_collection", return_value=self.search_click_logs_collection),
            patch("apps.search.recommender.get_meeting_minutes_collection", return_value=self.meeting_minutes_collection),
            patch("apps.search.recommender.get_meeting_items_collection", return_value=self.meeting_items_collection),
            patch("apps.search.stats.get_search_logs_collection", return_value=self.search_logs_collection),
            patch("apps.search.stats.get_search_click_logs_collection", return_value=self.search_click_logs_collection),
            patch("apps.search.stats.get_meeting_items_collection", return_value=self.meeting_items_collection),
            patch("apps.search.views.get_related_meetings", side_effect=self._delegate_related_meetings),
            patch("apps.search.views.get_related_items", side_effect=self._delegate_related_items),
            patch("apps.search.views.get_stats", side_effect=self._delegate_stats),
        ]
        for patcher in self.patchers:
            patcher.start()

        self._seed_documents()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        super().tearDown()

    def test_search_returns_score_detail_highlights_and_logs_search(self):
        response = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Search completed.")
        self.assertEqual(response.data["data"]["query"], "FDA")
        self.assertEqual(response.data["data"]["total"], 2)

        result = response.data["data"]["results"][0]
        self.assertEqual(result["meeting_id"], "meet_001")
        self.assertGreater(result["final_score"], 0)
        self.assertEqual(result["score_detail"]["keyword_score"], 8.0)
        self.assertEqual(result["score_detail"]["structure_score"], 4.0)
        self.assertEqual(result["score_detail"]["task_score"], 0.0)
        self.assertEqual(result["score_detail"]["feedback_score"], 0.0)
        self.assertIn("item_content", result["matched_fields"])
        self.assertEqual(result["matched_snippets"][0]["field"], "content")
        self.assertIn("<mark>FDA</mark>", result["matched_snippets"][0]["snippet"])
        self.assertEqual(result["matched_items"][0]["item_id"], "item_003")
        self.assertEqual(result["matched_items"][0]["score_detail"]["keyword_score"], 8.0)
        self.assertEqual(result["matched_items"][0]["score_detail"]["structure_score"], 4.0)

        self.assertEqual(len(self.search_logs_collection.documents), 1)
        search_log = self.search_logs_collection.documents[0]
        self.assertEqual(search_log["query"], "FDA")
        self.assertEqual(search_log["result_count"], 2)
        self.assertEqual(search_log["result_meeting_ids"][0], "meet_001")

    def test_search_supports_item_state_filters_and_owner_filter(self):
        response = self.client.get(
            reverse("meeting-minutes-search"),
            {
                "has_owner": "true",
                "has_planned_date": "true",
                "is_completed": "false",
                "has_tracking_result": "false",
                "owner": "倪仲達",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["total"], 2)
        result = response.data["data"]["results"][0]
        self.assertEqual(result["meeting_id"], "meet_001")
        self.assertEqual(len(result["matched_items"]), 1)
        self.assertEqual(result["matched_items"][0]["item_id"], "item_001")

    def test_feedback_score_increases_after_click(self):
        first_response = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})
        search_id = first_response.data["data"]["search_id"]

        click_response = self.client.post(
            reverse("search-click-log"),
            {
                "search_id": search_id,
                "meeting_id": "meet_001",
                "item_id": "item_003",
                "document_id": "doc_001",
            },
            format="json",
        )
        self.assertEqual(click_response.status_code, status.HTTP_201_CREATED)

        second_response = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})
        result = second_response.data["data"]["results"][0]

        self.assertEqual(result["score_detail"]["feedback_score"], 2.5)
        self.assertEqual(result["matched_items"][0]["score_detail"]["feedback_score"], 1.5)

    def test_search_includes_graph_score_and_expanded_keywords_when_graph_matches_exist(self):
        with patch(
            "apps.search.services.get_graph_score_context",
            return_value={
                "expanded_keywords": ["TFDA", "CFDA"],
                "meeting_scores": {"meet_001": 2.5},
                "item_scores": {"item_003": 1.5},
                "matches": [],
            },
        ):
            response = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["expanded_keywords_from_graph"], ["TFDA", "CFDA"])
        result = next(item for item in response.data["data"]["results"] if item["meeting_id"] == "meet_001")
        self.assertEqual(result["score_detail"]["graph_score"], 2.5)
        matched_item = next(item for item in result["matched_items"] if item["item_id"] == "item_003")
        self.assertEqual(matched_item["score_detail"]["graph_score"], 1.5)

    def test_related_meetings_returns_reasoned_matches(self):
        response = self.client.get(reverse("related-meetings", args=["meet_001"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["meeting_id"], "meet_001")
        related = response.data["data"]["related_meetings"]
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0]["meeting_id"], "meet_003")
        self.assertTrue(any("same responsible_unit" in reason or "shared owner" in reason for reason in related[0]["reason"]))

    def test_related_items_returns_reasoned_matches(self):
        response = self.client.get(reverse("related-items", args=["item_001"]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        related_items = response.data["data"]["related_items"]
        self.assertGreaterEqual(len(related_items), 1)
        self.assertEqual(related_items[0]["item_id"], "item_005")
        self.assertTrue(any("same owner" in reason or "shared keyword" in reason for reason in related_items[0]["reason"]))

    def test_search_stats_returns_aggregates(self):
        first_search = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})
        second_search = self.client.get(reverse("meeting-minutes-search"), {"q": "Conformity"})

        self.client.post(
            reverse("search-click-log"),
            {
                "search_id": first_search.data["data"]["search_id"],
                "meeting_id": "meet_001",
                "item_id": "item_003",
                "document_id": "doc_001",
            },
            format="json",
        )
        self.client.post(
            reverse("search-click-log"),
            {
                "search_id": second_search.data["data"]["search_id"],
                "meeting_id": "meet_003",
                "item_id": "item_005",
                "document_id": "doc_003",
            },
            format="json",
        )

        response = self.client.get(reverse("search-stats"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data["data"]
        self.assertEqual(data["total_search_count"], 2)
        self.assertEqual(data["total_click_count"], 2)
        self.assertEqual(data["top_queries"][0]["query"], "FDA")
        self.assertEqual(data["top_clicked_meetings"][0]["meeting_id"], "meet_001")
        self.assertTrue(any(entry["owner"] == "倪仲達" for entry in data["top_owners"]))
        self.assertEqual(len(data["recent_searches"]), 2)

    def test_invalid_boolean_filter_returns_400(self):
        response = self.client.get(reverse("meeting-minutes-search"), {"has_owner": "maybe"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])

    def _delegate_related_meetings(self, meeting_id, limit=10):
        from apps.search.services import get_related_meetings

        return get_related_meetings(meeting_id, limit=limit)

    def _delegate_related_items(self, item_id, limit=10):
        from apps.search.services import get_related_items

        return get_related_items(item_id, limit=limit)

    def _delegate_stats(self, limit=10):
        from apps.search.services import get_stats

        return get_stats(limit=limit)

    def _seed_documents(self):
        self.meeting_minutes_collection.insert_many(
            [
                {
                    "meeting_id": "meet_001",
                    "document_id": "doc_001",
                    "meeting_name": "Conformity stem 原型確認會議",
                    "meeting_date": "2018-04-03",
                    "responsible_unit": "UR3",
                    "chairperson": "倪仲達",
                    "recorder": "林怡君",
                    "attendees": ["倪仲達", "黃志宏", "UPD"],
                    "location": "TP_A",
                    "status": "parsed",
                    "created_at": datetime(2026, 5, 1, 8, 0, tzinfo=dt_timezone.utc),
                    "updated_at": datetime(2026, 5, 1, 8, 30, tzinfo=dt_timezone.utc),
                },
                {
                    "meeting_id": "meet_002",
                    "document_id": "doc_002",
                    "meeting_name": "Instrument planning meeting",
                    "meeting_date": "2018-09-13",
                    "responsible_unit": "UR4",
                    "chairperson": "陳美玲",
                    "recorder": "周佩珊",
                    "attendees": ["陳美玲"],
                    "location": "TP_B",
                    "status": "parsed",
                    "created_at": datetime(2026, 5, 2, 8, 0, tzinfo=dt_timezone.utc),
                    "updated_at": datetime(2026, 5, 2, 8, 30, tzinfo=dt_timezone.utc),
                },
                {
                    "meeting_id": "meet_003",
                    "document_id": "doc_003",
                    "meeting_name": "Conformity stem 設計追蹤會議",
                    "meeting_date": "2018-04-10",
                    "responsible_unit": "UR3",
                    "chairperson": "王建明",
                    "recorder": "李佳欣",
                    "attendees": ["倪仲達", "UPD"],
                    "location": "TP_A",
                    "status": "parsed",
                    "created_at": datetime(2026, 5, 3, 8, 0, tzinfo=dt_timezone.utc),
                    "updated_at": datetime(2026, 5, 3, 8, 30, tzinfo=dt_timezone.utc),
                },
            ]
        )

        self.meeting_items_collection.insert_many(
            [
                {
                    "item_id": "item_001",
                    "meeting_id": "meet_001",
                    "document_id": "doc_001",
                    "item_no": "01",
                    "content": "確認 Conformity stem 打樣尺寸與後續驗證時程",
                    "owner": "倪仲達",
                    "planned_date": "2018-04-20",
                    "actual_completed_date": None,
                    "tracking_result": None,
                },
                {
                    "item_id": "item_002",
                    "meeting_id": "meet_001",
                    "document_id": "doc_001",
                    "item_no": "02",
                    "content": "TFDA 文件補件規劃",
                    "owner": "倪仲達",
                    "planned_date": "2018-04-13",
                    "actual_completed_date": "2018-04-13",
                    "tracking_result": "已完成補件",
                },
                {
                    "item_id": "item_003",
                    "meeting_id": "meet_001",
                    "document_id": "doc_001",
                    "item_no": "03",
                    "content": "產品預計申請地區為: CE, FDA, TFDA, CFDA",
                    "owner": "UPD",
                    "planned_date": None,
                    "actual_completed_date": None,
                    "tracking_result": None,
                },
                {
                    "item_id": "item_004",
                    "meeting_id": "meet_002",
                    "document_id": "doc_002",
                    "item_no": "01",
                    "content": "建立 instrument planning 基準版本",
                    "owner": "周佩珊",
                    "planned_date": "2018-09-20",
                    "actual_completed_date": None,
                    "tracking_result": None,
                },
                {
                    "item_id": "item_005",
                    "meeting_id": "meet_003",
                    "document_id": "doc_003",
                    "item_no": "01",
                    "content": "Conformity stem 驗證進度追蹤與 FDA 文件準備",
                    "owner": "倪仲達",
                    "planned_date": "2018-04-25",
                    "actual_completed_date": None,
                    "tracking_result": None,
                },
                {
                    "item_id": "item_006",
                    "meeting_id": "meet_003",
                    "document_id": "doc_003",
                    "item_no": "02",
                    "content": "追蹤供應商回覆",
                    "owner": "--",
                    "planned_date": None,
                    "actual_completed_date": None,
                    "tracking_result": "",
                },
            ]
        )
