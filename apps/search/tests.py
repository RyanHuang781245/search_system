from django.urls import reverse
from rest_framework import status
from rest_framework.test import APISimpleTestCase
from unittest.mock import patch


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

    def find(self, query, projection=None):
        results = [self._project(document, projection) for document in self.documents if self._matches(document, query)]
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
            if key == "$or":
                if not any(self._matches(document, clause) for clause in expected):
                    return False
                continue

            value = document.get(key)
            if isinstance(expected, dict):
                if "$regex" in expected:
                    haystack = str(value or "")
                    needle = str(expected["$regex"])
                    if "i" in expected.get("$options", ""):
                        haystack = haystack.lower()
                        needle = needle.lower()
                    if needle not in haystack:
                        return False
                    continue
                if "$elemMatch" in expected:
                    regex = expected["$elemMatch"].get("$regex", "")
                    options = expected["$elemMatch"].get("$options", "")
                    haystack = [str(item) for item in value or []]
                    if "i" in options:
                        haystack = [item.lower() for item in haystack]
                        regex = regex.lower()
                    if not any(regex in item for item in haystack):
                        return False
                    continue
                if "$gte" in expected or "$lte" in expected:
                    if value is None:
                        return False
                    if "$gte" in expected and value < expected["$gte"]:
                        return False
                    if "$lte" in expected and value > expected["$lte"]:
                        return False
                    continue
            if value != expected:
                return False
        return True


class SearchAPITestCase(APISimpleTestCase):
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
        ]
        for patcher in self.patchers:
            patcher.start()

        self._seed_search_documents()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        super().tearDown()

    def test_search_q_fda_returns_meeting_with_ranked_items_and_writes_search_log(self):
        response = self.client.get(reverse("meeting-minutes-search"), {"q": "FDA"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["message"], "Search completed.")
        self.assertEqual(response.data["data"]["query"], "FDA")
        self.assertEqual(response.data["data"]["total"], 1)

        result = response.data["data"]["results"][0]
        self.assertEqual(result["meeting_id"], "meet_001")
        self.assertEqual(result["score"], 8)
        self.assertIn("item_content", result["matched_fields"])
        self.assertEqual(len(result["matched_items"]), 1)
        self.assertEqual(result["matched_items"][0]["item_id"], "item_003")
        self.assertEqual(result["matched_items"][0]["score"], 8)

        self.assertEqual(len(self.search_logs_collection.documents), 1)
        search_log = self.search_logs_collection.documents[0]
        self.assertEqual(search_log["query"], "FDA")
        self.assertEqual(search_log["result_count"], 1)
        self.assertEqual(search_log["result_meeting_ids"], ["meet_001"])

    def test_search_supports_metadata_ranking_and_filters(self):
        response = self.client.get(
            reverse("meeting-minutes-search"),
            {
                "q": "Conformity stem",
                "date_from": "2018-04-01",
                "date_to": "2018-04-30",
                "responsible_unit": "UR3",
                "chairperson": "倪仲達",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["total"], 1)
        result = response.data["data"]["results"][0]
        self.assertEqual(result["meeting_id"], "meet_001")
        self.assertEqual(result["score"], 10)
        self.assertIn("meeting_name", result["matched_fields"])

    def test_search_supports_owner_filter_without_keyword_and_logs_click(self):
        response = self.client.get(reverse("meeting-minutes-search"), {"owner": "倪仲達"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["total"], 1)
        result = response.data["data"]["results"][0]
        self.assertEqual(result["meeting_id"], "meet_001")
        self.assertEqual(len(result["matched_items"]), 2)

        search_id = response.data["data"]["search_id"]
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
        self.assertTrue(click_response.data["success"])
        self.assertEqual(len(self.search_click_logs_collection.documents), 1)
        click_log = self.search_click_logs_collection.documents[0]
        self.assertEqual(click_log["search_id"], search_id)
        self.assertEqual(click_log["query"], "")
        self.assertEqual(click_log["meeting_id"], "meet_001")
        self.assertEqual(click_log["item_id"], "item_003")

    def _seed_search_documents(self):
        self.meeting_minutes_collection.insert_one(
            {
                "meeting_id": "meet_001",
                "document_id": "doc_001",
                "meeting_name": "Conformity stem 原型確認會議",
                "meeting_date": "2018-04-03",
                "responsible_unit": "UR3",
                "chairperson": "倪仲達",
                "recorder": "倪仲達",
                "attendees": ["劉育良", "陳文全", "倪仲達"],
                "location": "HC_55A, TP_A",
                "status": "parsed",
            }
        )
        self.meeting_minutes_collection.insert_one(
            {
                "meeting_id": "meet_002",
                "document_id": "doc_002",
                "meeting_name": "Instrument planning meeting",
                "meeting_date": "2018-09-13",
                "responsible_unit": "UR4",
                "chairperson": "林延生",
                "recorder": "梁誌明",
                "attendees": ["林延生"],
                "location": "TP_A",
                "status": "parsed",
            }
        )

        self.meeting_items_collection.insert_one(
            {
                "item_id": "item_001",
                "meeting_id": "meet_001",
                "document_id": "doc_001",
                "item_no": "01",
                "content": "評估 cemented stem 的開發與送件時間",
                "owner": "倪仲達",
                "planned_date": "2018-04-20",
                "actual_completed_date": None,
                "tracking_result": None,
            }
        )
        self.meeting_items_collection.insert_one(
            {
                "item_id": "item_002",
                "meeting_id": "meet_001",
                "document_id": "doc_001",
                "item_no": "02",
                "content": "與 UR4 法規確認 TFDA 工單樣品數量",
                "owner": "倪仲達",
                "planned_date": "2018-04-13",
                "actual_completed_date": "2018-04-13",
                "tracking_result": None,
            }
        )
        self.meeting_items_collection.insert_one(
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
            }
        )
        self.meeting_items_collection.insert_one(
            {
                "item_id": "item_004",
                "meeting_id": "meet_002",
                "document_id": "doc_002",
                "item_no": "01",
                "content": "討論器械工程圖時程",
                "owner": "梁誌明",
                "planned_date": "2018-09-20",
                "actual_completed_date": None,
                "tracking_result": None,
            }
        )
