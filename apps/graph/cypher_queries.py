MERGE_DOCUMENT = """
MERGE (d:Document {document_id: $document_id})
SET d.original_filename = $original_filename
"""

MERGE_MEETING = """
MERGE (m:Meeting {meeting_id: $meeting_id})
SET m.meeting_name = $meeting_name,
    m.meeting_date = $meeting_date,
    m.responsible_unit = $responsible_unit
"""

MERGE_HAS_MEETING = """
MATCH (d:Document {document_id: $document_id})
MATCH (m:Meeting {meeting_id: $meeting_id})
MERGE (d)-[:HAS_MEETING]->(m)
"""

MERGE_MEETING_ITEM = """
MERGE (i:MeetingItem {item_id: $item_id})
SET i.item_no = $item_no,
    i.content = $content,
    i.planned_date = $planned_date,
    i.actual_completed_date = $actual_completed_date
"""

MERGE_DATE = """
MERGE (d:Date {date_value: $date_value, date_type: $date_type})
"""

MERGE_HAS_ITEM = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (i:MeetingItem {item_id: $item_id})
MERGE (m)-[:HAS_ITEM]->(i)
"""

MERGE_HAS_PLANNED_DATE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Date {date_value: $date_value, date_type: 'planned'})
MERGE (i)-[:HAS_PLANNED_DATE]->(d)
"""

MERGE_HAS_COMPLETED_DATE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Date {date_value: $date_value, date_type: 'completed'})
MERGE (i)-[:HAS_COMPLETED_DATE]->(d)
"""

MERGE_PERSON = """
MERGE (p:Person {name: $name})
"""

MERGE_UNIT = """
MERGE (u:Unit {name: $name})
"""

MERGE_CHAIRED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:CHAIRED_BY]->(p)
"""

MERGE_RECORDED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:RECORDED_BY]->(p)
"""

MERGE_ATTENDED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:ATTENDED_BY]->(p)
"""

MERGE_BELONGS_TO_UNIT = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (u:Unit {name: $unit_name})
MERGE (m)-[:BELONGS_TO_UNIT]->(u)
"""

MERGE_RESPONSIBLE_BY = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (p:Person {name: $person_name})
MERGE (i)-[:RESPONSIBLE_BY]->(p)
"""

MERGE_KEYWORD = """
MERGE (k:Keyword {name: $name})
SET k.type = $type
"""

MERGE_PRODUCT = """
MERGE (p:Product {name: $name})
"""

MERGE_REGULATION = """
MERGE (r:Regulation {name: $name})
"""

MERGE_MENTIONS_KEYWORD = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (k:Keyword {name: $keyword_name})
MERGE (i)-[r:MENTIONS {field: $field}]->(k)
SET r.field = $field,
    r.score = $score,
    r.method = $method
"""

MERGE_MEETING_MENTIONS_KEYWORD = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (k:Keyword {name: $keyword_name})
MERGE (m)-[r:MENTIONS {field: $field}]->(k)
SET r.field = $field,
    r.score = $score,
    r.method = $method
"""

MERGE_MENTIONS_PRODUCT = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (p:Product {name: $product_name})
MERGE (i)-[:MENTIONS_PRODUCT]->(p)
"""

MERGE_MENTIONS_REGULATION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (r:Regulation {name: $regulation_name})
MERGE (i)-[:MENTIONS_REGULATION]->(r)
"""

MERGE_CO_OCCURS_WITH = """
MATCH (a:Keyword {name: $left_keyword})
MATCH (b:Keyword {name: $right_keyword})
MERGE (a)-[r:CO_OCCURS_WITH]->(b)
SET r.count = $count,
    r.weight = $weight
"""

QUERY_RELATED_KEYWORDS = """
MATCH (base:Keyword)-[r:CO_OCCURS_WITH]-(related:Keyword)
WHERE toUpper(base.name) = toUpper(trim($keyword))
  AND toUpper(related.name) <> toUpper(trim($keyword))
RETURN related.name AS keyword,
       related.type AS type,
       max(r.weight) AS weight,
       max(r.count) AS count
ORDER BY weight DESC, count DESC, keyword ASC
LIMIT $limit
"""

QUERY_GRAPH_SEARCH = """
MATCH (item:MeetingItem)-[mention:MENTIONS]->(keyword:Keyword)
WHERE toUpper(keyword.name) IN $keywords
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       keyword.name AS matched_keyword,
       keyword.type AS keyword_type,
       mention.field AS matched_field,
       mention.score AS keyword_score,
       mention.method AS keyword_method
UNION
MATCH (meeting:Meeting)-[mention:MENTIONS]->(keyword:Keyword)
WHERE toUpper(keyword.name) IN $keywords
MATCH (meeting)-[:HAS_ITEM]->(item:MeetingItem)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       keyword.name AS matched_keyword,
       keyword.type AS keyword_type,
       mention.field AS matched_field,
       mention.score AS keyword_score,
       mention.method AS keyword_method
"""
