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

MERGE_ACTION_ITEM = """
MERGE (a:ActionItem {action_id: $action_id})
SET a.title = $title,
    a.status = $status,
    a.content = $content,
    a.tracking_result = $tracking_result,
    a.planned_date = $planned_date,
    a.actual_completed_date = $actual_completed_date
"""

MERGE_HAS_ACTION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (a:ActionItem {action_id: $action_id})
MERGE (i)-[:HAS_ACTION]->(a)
"""

MERGE_ACTION_ASSIGNED_TO = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (p:Person {name: $person_name})
MERGE (a)-[:ASSIGNED_TO]->(p)
"""

MERGE_ACTION_TARGETS_PRODUCT = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (p:Product {name: $product_name})
MERGE (a)-[:TARGETS_PRODUCT]->(p)
"""

MERGE_ACTION_CONSTRAINED_BY = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (r:Regulation {name: $regulation_name})
MERGE (a)-[:CONSTRAINED_BY]->(r)
"""

MERGE_DECISION = """
MERGE (d:Decision {decision_id: $decision_id})
SET d.title = $title,
    d.evidence = $evidence
"""

MERGE_HAS_DECISION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Decision {decision_id: $decision_id})
MERGE (i)-[:HAS_DECISION]->(d)
"""

MERGE_RISK = """
MERGE (r:Risk {risk_id: $risk_id})
SET r.name = $name,
    r.evidence = $evidence,
    r.severity = $severity
"""

MERGE_HAS_RISK = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (r:Risk {risk_id: $risk_id})
MERGE (i)-[:HAS_RISK]->(r)
"""

MERGE_ISSUE = """
MERGE (issue:Issue {issue_id: $issue_id})
SET issue.title = $title,
    issue.signature = $signature
"""

MERGE_TRACKS_ISSUE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (i)-[:TRACKS_ISSUE]->(issue)
"""

MERGE_DECIDES_ON_ISSUE = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (d)-[:DECIDES_ON]->(issue)
"""

MERGE_RISK_OF_ISSUE = """
MATCH (r:Risk {risk_id: $risk_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (r)-[:RISK_OF]->(issue)
"""

MERGE_FOLLOW_UP_OF = """
MATCH (current:MeetingItem {item_id: $current_item_id})
MATCH (previous:MeetingItem {item_id: $previous_item_id})
MERGE (current)-[:FOLLOW_UP_OF]->(previous)
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

QUERY_RESPONSIBLE_ITEMS = """
MATCH (item:MeetingItem)-[:RESPONSIBLE_BY]->(person:Person)
WHERE $entity = "" OR toUpper(person.name) CONTAINS $entity
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       person.name AS matched_entity,
       "RESPONSIBLE_BY" AS matched_relation,
       "owner" AS matched_field
"""

QUERY_MEETING_PERSON_RELATION = """
MATCH (meeting:Meeting)-[relation]->(person:Person)
WHERE type(relation) = $relation
  AND ($entity = "" OR toUpper(person.name) CONTAINS $entity)
MATCH (meeting)-[:HAS_ITEM]->(item:MeetingItem)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       person.name AS matched_entity,
       type(relation) AS matched_relation,
       toLower(replace(type(relation), "_BY", "")) AS matched_field
"""

QUERY_UNIT_MEETINGS = """
MATCH (meeting:Meeting)-[:BELONGS_TO_UNIT]->(unit:Unit)
WHERE $entity = "" OR toUpper(unit.name) CONTAINS $entity
MATCH (meeting)-[:HAS_ITEM]->(item:MeetingItem)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       unit.name AS matched_entity,
       "BELONGS_TO_UNIT" AS matched_relation,
       "responsible_unit" AS matched_field
"""

QUERY_ITEM_DATE_RELATION = """
MATCH (item:MeetingItem)-[relation]->(date_node:Date)
WHERE type(relation) = $relation
  AND ($entity = "" OR toUpper(date_node.date_value) CONTAINS $entity)
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       date_node.date_value AS matched_entity,
       type(relation) AS matched_relation,
       CASE type(relation)
         WHEN "HAS_PLANNED_DATE" THEN "planned_date"
         ELSE "actual_completed_date"
       END AS matched_field
"""

QUERY_ITEM_PRODUCT_RELATION = """
MATCH (item:MeetingItem)-[:MENTIONS_PRODUCT]->(product:Product)
WHERE $entity = "" OR toUpper(product.name) CONTAINS $entity
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       product.name AS matched_entity,
       "MENTIONS_PRODUCT" AS matched_relation,
       "content" AS matched_field
"""

QUERY_ITEM_REGULATION_RELATION = """
MATCH (item:MeetingItem)-[:MENTIONS_REGULATION]->(regulation:Regulation)
WHERE $entity = "" OR toUpper(regulation.name) CONTAINS $entity
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       regulation.name AS matched_entity,
       "MENTIONS_REGULATION" AS matched_relation,
       "content" AS matched_field
"""

QUERY_COMPOSITE_GRAPH_SEARCH = """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (item)-[:HAS_DECISION]->(decision:Decision)
OPTIONAL MATCH (item)-[:HAS_RISK]->(risk:Risk)
OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)
WHERE ($target <> "action_items" OR action IS NOT NULL)
  AND ($target <> "decisions" OR decision IS NOT NULL)
  AND ($target <> "risks" OR risk IS NOT NULL)
  AND ($target <> "issues" OR issue IS NOT NULL)
  AND (
    $person = "" OR
    EXISTS {
      MATCH (item)-[:RESPONSIBLE_BY]->(owner:Person)
      WHERE toUpper(owner.name) CONTAINS $person
    } OR
    EXISTS {
      MATCH (action)-[:ASSIGNED_TO]->(assignee:Person)
      WHERE toUpper(assignee.name) CONTAINS $person
    }
  )
  AND (
    $unit = "" OR
    EXISTS {
      MATCH (meeting)-[:BELONGS_TO_UNIT]->(unit:Unit)
      WHERE toUpper(unit.name) CONTAINS $unit
    }
  )
  AND (
    $product = "" OR
    EXISTS {
      MATCH (item)-[:MENTIONS_PRODUCT]->(product:Product)
      WHERE toUpper(product.name) CONTAINS $product
    } OR
    EXISTS {
      MATCH (action)-[:TARGETS_PRODUCT]->(action_product:Product)
      WHERE toUpper(action_product.name) CONTAINS $product
    }
  )
  AND (
    $regulation = "" OR
    EXISTS {
      MATCH (item)-[:MENTIONS_REGULATION]->(regulation:Regulation)
      WHERE toUpper(regulation.name) CONTAINS $regulation
    } OR
    EXISTS {
      MATCH (action)-[:CONSTRAINED_BY]->(action_regulation:Regulation)
      WHERE toUpper(action_regulation.name) CONTAINS $regulation
    }
  )
  AND (
    $status = "" OR
    ($status = "completed" AND (action.status = "completed" OR item.actual_completed_date IS NOT NULL)) OR
    ($status = "in_progress" AND action.status = "in_progress") OR
    ($status = "pending" AND action.status = "pending") OR
    ($status = "not_completed" AND coalesce(action.status, "pending") <> "completed" AND item.actual_completed_date IS NULL)
  )
  AND (
    $keyword = "" OR
    toUpper(coalesce(item.content, "")) CONTAINS $keyword OR
    toUpper(coalesce(action.title, "")) CONTAINS $keyword OR
    toUpper(coalesce(decision.title, "")) CONTAINS $keyword OR
    toUpper(coalesce(risk.name, "")) CONTAINS $keyword OR
    toUpper(coalesce(issue.title, "")) CONTAINS $keyword OR
    EXISTS {
      MATCH (item)-[:MENTIONS]->(keyword:Keyword)
      WHERE toUpper(keyword.name) CONTAINS $keyword
    }
  )
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       CASE $target
         WHEN "decisions" THEN decision.title
         WHEN "risks" THEN risk.name
         WHEN "issues" THEN issue.title
         ELSE action.title
       END AS matched_entity,
       CASE $target
         WHEN "decisions" THEN "HAS_DECISION"
         WHEN "risks" THEN "HAS_RISK"
         WHEN "issues" THEN "TRACKS_ISSUE"
         ELSE "HAS_ACTION"
       END AS matched_relation,
       CASE $target
         WHEN "decisions" THEN decision.decision_id
         WHEN "risks" THEN risk.risk_id
         WHEN "issues" THEN issue.issue_id
         ELSE action.action_id
       END AS matched_node_id,
       $target AS matched_field,
       coalesce(action.status, "") AS semantic_status,
       [(item)-[:RESPONSIBLE_BY]->(owner:Person) | owner.name] AS owner_names,
       [(action)-[:ASSIGNED_TO]->(assignee:Person) | assignee.name] AS assignee_names,
       [(meeting)-[:BELONGS_TO_UNIT]->(unit:Unit) | unit.name] AS unit_names,
       [(item)-[:MENTIONS_PRODUCT]->(product:Product) | product.name] AS product_names,
       [(action)-[:TARGETS_PRODUCT]->(action_product:Product) | action_product.name] AS action_product_names,
       [(item)-[:MENTIONS_REGULATION]->(regulation:Regulation) | regulation.name] AS regulation_names,
       [(action)-[:CONSTRAINED_BY]->(action_regulation:Regulation) | action_regulation.name] AS action_regulation_names,
       [(item)-[:MENTIONS]->(keyword:Keyword) | keyword.name] AS keyword_names
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
"""

QUERY_FOLLOW_UP_ITEMS = """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)-[:FOLLOW_UP_OF]->(previous:MeetingItem)
OPTIONAL MATCH (previous_meeting:Meeting)-[:HAS_ITEM]->(previous)
OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)
WHERE (
    $keyword = "" OR
    toUpper(coalesce(item.content, "")) CONTAINS $keyword OR
    toUpper(coalesce(previous.content, "")) CONTAINS $keyword OR
    toUpper(coalesce(issue.title, "")) CONTAINS $keyword
  )
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       previous.item_id AS matched_entity,
       "FOLLOW_UP_OF" AS matched_relation,
       previous.item_id AS matched_node_id,
       "follow_up" AS matched_field,
       previous_meeting.meeting_id AS previous_meeting_id
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
"""
