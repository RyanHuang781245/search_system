# 建立或更新 Document 節點：代表一份上傳文件。
MERGE_DOCUMENT = """
MERGE (d:Document {document_id: $document_id})
SET d.original_filename = $original_filename
"""

# 建立或更新 Meeting 節點：代表一場會議，保存會議名稱、日期與主責單位。
MERGE_MEETING = """
MERGE (m:Meeting {meeting_id: $meeting_id})
SET m.meeting_name = $meeting_name,
    m.meeting_date = $meeting_date,
    m.responsible_unit = $responsible_unit
"""

# 建立 Document -> Meeting 的 HAS_MEETING 關聯：表示某份文件解析出某場會議。
MERGE_HAS_MEETING = """
MATCH (d:Document {document_id: $document_id})
MATCH (m:Meeting {meeting_id: $meeting_id})
MERGE (d)-[:HAS_MEETING]->(m)
"""

# 建立或更新 MeetingItem 節點：代表一筆會議議案，item_id 是跨 MongoDB / Neo4j / Qdrant 對齊的主鍵。
MERGE_MEETING_ITEM = """
MERGE (i:MeetingItem {item_id: $item_id})
SET i.item_no = $item_no,
    i.content = $content,
    i.planned_date = $planned_date,
    i.actual_completed_date = $actual_completed_date,
    i.status = $status,
    i.status_source = $status_source,
    i.status_confidence = $status_confidence
"""

# 建立 Date 節點：代表預計完成日或實際完成日。
MERGE_DATE = """
MERGE (d:Date {date_value: $date_value, date_type: $date_type})
"""

# 建立 Meeting -> MeetingItem 的 HAS_ITEM 關聯：表示某場會議包含某筆議案。
MERGE_HAS_ITEM = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (i:MeetingItem {item_id: $item_id})
MERGE (m)-[:HAS_ITEM]->(i)
"""

# 建立 MeetingItem -> Date 的 HAS_PLANNED_DATE 關聯：表示議案的預計完成日。
MERGE_HAS_PLANNED_DATE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Date {date_value: $date_value, date_type: 'planned'})
MERGE (i)-[:HAS_PLANNED_DATE]->(d)
"""

# 建立 MeetingItem -> Date 的 HAS_COMPLETED_DATE 關聯：表示議案的實際完成日。
MERGE_HAS_COMPLETED_DATE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Date {date_value: $date_value, date_type: 'completed'})
MERGE (i)-[:HAS_COMPLETED_DATE]->(d)
"""

# 重建單一議案前，先清掉由 MeetingItem 延伸出的舊關聯，避免重建圖譜時殘留過期關係。
CLEAR_MEETING_ITEM_DERIVED_RELATIONS = """
MATCH (i:MeetingItem {item_id: $item_id})
OPTIONAL MATCH (i)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (action)-[action_rel:ASSIGNED_TO|TARGETS_PRODUCT|CONSTRAINED_BY]->()
DELETE action_rel
WITH i
OPTIONAL MATCH (i)-[out_rel:HAS_PLANNED_DATE|HAS_COMPLETED_DATE|RESPONSIBLE_BY|MENTIONS|MENTIONS_PRODUCT|MENTIONS_REGULATION|HAS_ACTION|HAS_DECISION|HAS_RISK|TRACKS_ISSUE|FOLLOW_UP_OF]->()
DELETE out_rel
WITH i
OPTIONAL MATCH ()-[in_rel:FOLLOW_UP_OF]->(i)
DELETE in_rel
"""

# 建立 Person 節點：代表主席、紀錄者、出席者、負責人或 action assignee。
MERGE_PERSON = """
MERGE (p:Person {name: $name})
"""

# 建立 Unit 節點：代表會議主責單位。
MERGE_UNIT = """
MERGE (u:Unit {name: $name})
"""

# 建立 Meeting -> Person 的 CHAIRED_BY 關聯：表示會議主席。
MERGE_CHAIRED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:CHAIRED_BY]->(p)
"""

# 建立 Meeting -> Person 的 RECORDED_BY 關聯：表示會議紀錄者。
MERGE_RECORDED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:RECORDED_BY]->(p)
"""

# 建立 Meeting -> Person 的 ATTENDED_BY 關聯：表示會議出席者。
MERGE_ATTENDED_BY = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (p:Person {name: $person_name})
MERGE (m)-[:ATTENDED_BY]->(p)
"""

# 建立 Meeting -> Unit 的 BELONGS_TO_UNIT 關聯：表示會議屬於或由某單位負責。
MERGE_BELONGS_TO_UNIT = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (u:Unit {name: $unit_name})
MERGE (m)-[:BELONGS_TO_UNIT]->(u)
"""

# 建立 MeetingItem -> Person 的 RESPONSIBLE_BY 關聯：表示議案負責人。
MERGE_RESPONSIBLE_BY = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (p:Person {name: $person_name})
MERGE (i)-[:RESPONSIBLE_BY]->(p)
"""

# 建立或更新 Keyword 節點：代表從會議或議案文字抽出的關鍵字。
MERGE_KEYWORD = """
MERGE (k:Keyword {name: $name})
SET k.type = $type
"""

# 建立 Product 節點：代表議案提到的產品、專案或品項。
MERGE_PRODUCT = """
MERGE (p:Product {name: $name})
"""

# 建立 Regulation 節點：代表議案提到的法規、標準或認證。
MERGE_REGULATION = """
MERGE (r:Regulation {name: $name})
"""

# 建立 MeetingItem -> Keyword 的 MENTIONS 關聯：表示議案內容或追蹤結果提到某關鍵字。
MERGE_MENTIONS_KEYWORD = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (k:Keyword {name: $keyword_name})
MERGE (i)-[r:MENTIONS {field: $field}]->(k)
SET r.field = $field,
    r.score = $score,
    r.method = $method
"""

# 建立 Meeting -> Keyword 的 MENTIONS 關聯：表示會議名稱或會議層級文字提到某關鍵字。
MERGE_MEETING_MENTIONS_KEYWORD = """
MATCH (m:Meeting {meeting_id: $meeting_id})
MATCH (k:Keyword {name: $keyword_name})
MERGE (m)-[r:MENTIONS {field: $field}]->(k)
SET r.field = $field,
    r.score = $score,
    r.method = $method
"""

# 建立 MeetingItem -> Product 的 MENTIONS_PRODUCT 關聯：表示議案提到某產品。
MERGE_MENTIONS_PRODUCT = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (p:Product {name: $product_name})
MERGE (i)-[:MENTIONS_PRODUCT]->(p)
"""

# 建立 MeetingItem -> Regulation 的 MENTIONS_REGULATION 關聯：表示議案提到某法規或認證。
MERGE_MENTIONS_REGULATION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (r:Regulation {name: $regulation_name})
MERGE (i)-[:MENTIONS_REGULATION]->(r)
"""

# 建立或更新 ActionItem 節點：代表從議案抽出的待辦、追蹤事項或行動項目。
MERGE_ACTION_ITEM = """
MERGE (a:ActionItem {action_id: $action_id})
SET a.title = $title,
    a.status = $status,
    a.status_source = $status_source,
    a.status_confidence = $status_confidence,
    a.content = $content,
    a.tracking_result = $tracking_result,
    a.planned_date = $planned_date,
    a.actual_completed_date = $actual_completed_date
"""

# 建立 MeetingItem -> ActionItem 的 HAS_ACTION 關聯：表示議案包含某個行動項目。
MERGE_HAS_ACTION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (a:ActionItem {action_id: $action_id})
MERGE (i)-[:HAS_ACTION]->(a)
"""

# 建立 ActionItem -> Person 的 ASSIGNED_TO 關聯：表示行動項目指派給某人。
MERGE_ACTION_ASSIGNED_TO = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (p:Person {name: $person_name})
MERGE (a)-[:ASSIGNED_TO]->(p)
"""

# 建立 ActionItem -> Product 的 TARGETS_PRODUCT 關聯：表示行動項目與某產品有關。
MERGE_ACTION_TARGETS_PRODUCT = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (p:Product {name: $product_name})
MERGE (a)-[:TARGETS_PRODUCT]->(p)
"""

# 建立 ActionItem -> Regulation 的 CONSTRAINED_BY 關聯：表示行動項目受某法規或認證限制。
MERGE_ACTION_CONSTRAINED_BY = """
MATCH (a:ActionItem {action_id: $action_id})
MATCH (r:Regulation {name: $regulation_name})
MERGE (a)-[:CONSTRAINED_BY]->(r)
"""

# 建立或更新 Decision 節點：代表從議案抽出的決議。
MERGE_DECISION = """
MERGE (d:Decision {decision_id: $decision_id})
SET d.title = $title,
    d.evidence = $evidence
"""

# 建立 MeetingItem -> Decision 的 HAS_DECISION 關聯：表示議案包含某個決議。
MERGE_HAS_DECISION = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (d:Decision {decision_id: $decision_id})
MERGE (i)-[:HAS_DECISION]->(d)
"""

# 建立或更新 Risk 節點：代表從議案抽出的風險。
MERGE_RISK = """
MERGE (r:Risk {risk_id: $risk_id})
SET r.name = $name,
    r.evidence = $evidence,
    r.severity = $severity
"""

# 建立 MeetingItem -> Risk 的 HAS_RISK 關聯：表示議案包含某個風險。
MERGE_HAS_RISK = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (r:Risk {risk_id: $risk_id})
MERGE (i)-[:HAS_RISK]->(r)
"""

# 建立或更新 Issue 節點：代表跨會議追蹤的議題。
MERGE_ISSUE = """
MERGE (issue:Issue {issue_id: $issue_id})
SET issue.title = $title,
    issue.signature = $signature
"""

# 建立 MeetingItem -> Issue 的 TRACKS_ISSUE 關聯：表示議案正在追蹤某個議題。
MERGE_TRACKS_ISSUE = """
MATCH (i:MeetingItem {item_id: $item_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (i)-[:TRACKS_ISSUE]->(issue)
"""

# 建立 Decision -> Issue 的 DECIDES_ON 關聯：表示某決議是針對某議題。
MERGE_DECIDES_ON_ISSUE = """
MATCH (d:Decision {decision_id: $decision_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (d)-[:DECIDES_ON]->(issue)
"""

# 建立 Risk -> Issue 的 RISK_OF 關聯：表示某風險屬於某議題。
MERGE_RISK_OF_ISSUE = """
MATCH (r:Risk {risk_id: $risk_id})
MATCH (issue:Issue {issue_id: $issue_id})
MERGE (r)-[:RISK_OF]->(issue)
"""

# 建立 MeetingItem -> MeetingItem 的 FOLLOW_UP_OF 關聯：表示目前議案追蹤前一筆相關議案。
MERGE_FOLLOW_UP_OF = """
MATCH (current:MeetingItem {item_id: $current_item_id})
MATCH (previous:MeetingItem {item_id: $previous_item_id})
MERGE (current)-[:FOLLOW_UP_OF]->(previous)
"""

# 建立 Keyword -> Keyword 的 CO_OCCURS_WITH 關聯：表示兩個關鍵字在議案中共同出現。
MERGE_CO_OCCURS_WITH = """
MATCH (a:Keyword {name: $left_keyword})
MATCH (b:Keyword {name: $right_keyword})
MERGE (a)-[r:CO_OCCURS_WITH]->(b)
SET r.count = $count,
    r.weight = $weight
"""

# 查詢與指定關鍵字共現的其他關鍵字。
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

# 依關鍵字查詢圖譜：找出提到指定關鍵字的議案或會議，回傳對應會議與議案。
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

# 查詢某人負責的議案：使用 MeetingItem -> Person 的 RESPONSIBLE_BY 關聯。
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

# 依問題中的會議名稱或 meeting_id 找出最匹配會議，並列出該會議全部議案。
QUERY_MEETING_ITEMS_BY_QUERY = """
MATCH (candidate:Meeting)
WITH candidate,
     CASE
       WHEN toUpper($question) CONTAINS toUpper(candidate.meeting_name) THEN 100
       WHEN toUpper($question) CONTAINS toUpper(candidate.meeting_id) THEN 95
       WHEN toUpper(candidate.meeting_name) CONTAINS toUpper($question) THEN 90
       ELSE size([term IN $terms WHERE toUpper(candidate.meeting_name) CONTAINS term OR toUpper(candidate.meeting_id) CONTAINS term])
     END AS match_score
WHERE match_score > 0
WITH max(match_score) AS best_score, collect({meeting: candidate, score: match_score}) AS candidates
UNWIND candidates AS candidate
WITH candidate.meeting AS meeting, candidate.score AS match_score, best_score
WHERE match_score = best_score
MATCH (meeting)-[:HAS_ITEM]->(item:MeetingItem)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       meeting.meeting_name AS matched_entity,
       "HAS_ITEM" AS matched_relation,
       "meeting_items" AS matched_field
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
"""

# 查詢會議與人員的關係，例如主席 CHAIRED_BY、紀錄者 RECORDED_BY、出席者 ATTENDED_BY。
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

# 查詢某單位相關會議及其議案：使用 Meeting -> Unit 的 BELONGS_TO_UNIT 關聯。
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

# 查詢議案日期關係：可查 HAS_PLANNED_DATE 或 HAS_COMPLETED_DATE。
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

# 查詢產品相關議案：使用 MeetingItem -> Product 的 MENTIONS_PRODUCT 關聯。
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

# 查詢法規或認證相關議案：使用 MeetingItem -> Regulation 的 MENTIONS_REGULATION 關聯。
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

# 複合圖譜查詢：同時篩選 action、decision、risk、issue 與人員、單位、產品、法規、狀態、關鍵字。
QUERY_COMPOSITE_GRAPH_SEARCH = """
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
OPTIONAL MATCH (item)-[:HAS_ACTION]->(action:ActionItem)
OPTIONAL MATCH (item)-[:HAS_DECISION]->(decision:Decision)
OPTIONAL MATCH (item)-[:HAS_RISK]->(risk:Risk)
OPTIONAL MATCH (item)-[:TRACKS_ISSUE]->(issue:Issue)
WITH meeting, item, action, decision, risk, issue
WHERE ($target <> 'action_items' OR action IS NOT NULL)
  AND ($target <> 'decisions' OR decision IS NOT NULL)
  AND ($target <> 'risks' OR risk IS NOT NULL)
  AND ($target <> 'issues' OR issue IS NOT NULL)
  AND (
    $person = '' OR
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
    $unit = '' OR
    EXISTS {
      MATCH (meeting)-[:BELONGS_TO_UNIT]->(unit:Unit)
      WHERE toUpper(unit.name) CONTAINS $unit
    }
  )
  AND (
    $product = '' OR
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
    $regulation = '' OR
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
    $status = '' OR
    ($status = 'completed' AND (
      (coalesce(item.actual_completed_date, '') <> '' AND NOT (replace(trim(toLower(coalesce(item.actual_completed_date, ''))), ' ', '') IN ['-', '--', 'na', 'n/a', 'none', 'null'])) OR
      (coalesce(action.actual_completed_date, '') <> '' AND NOT (replace(trim(toLower(coalesce(action.actual_completed_date, ''))), ' ', '') IN ['-', '--', 'na', 'n/a', 'none', 'null'])) OR
      (action.status = 'completed' AND action.status_confidence = 'high')
    )) OR
    ($status = 'in_progress' AND action.status = 'in_progress') OR
    ($status = 'pending' AND action.status = 'pending') OR
    ($status = 'not_completed' AND (
      coalesce(item.actual_completed_date, '') = '' OR replace(trim(toLower(coalesce(item.actual_completed_date, ''))), ' ', '') IN ['-', '--', 'na', 'n/a', 'none', 'null']
    ) AND (
      coalesce(action.actual_completed_date, '') = '' OR replace(trim(toLower(coalesce(action.actual_completed_date, ''))), ' ', '') IN ['-', '--', 'na', 'n/a', 'none', 'null']
    ) AND NOT (coalesce(action.status, 'pending') IN ['completed', 'not_applicable'])) OR
    ($status = 'not_applicable' AND action.status = 'not_applicable')
  )
  AND (
    $keyword = '' OR
    toUpper(coalesce(item.content, '')) CONTAINS $keyword OR
    toUpper(coalesce(action.title, '')) CONTAINS $keyword OR
    toUpper(coalesce(decision.title, '')) CONTAINS $keyword OR
    toUpper(coalesce(risk.name, '')) CONTAINS $keyword OR
    toUpper(coalesce(issue.title, '')) CONTAINS $keyword OR
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
         WHEN 'decisions' THEN decision.title
         WHEN 'risks' THEN risk.name
         WHEN 'issues' THEN issue.title
         ELSE action.title
       END AS matched_entity,
       CASE $target
         WHEN 'decisions' THEN 'HAS_DECISION'
         WHEN 'risks' THEN 'HAS_RISK'
         WHEN 'issues' THEN 'TRACKS_ISSUE'
         ELSE 'HAS_ACTION'
       END AS matched_relation,
       CASE $target
         WHEN 'decisions' THEN decision.decision_id
         WHEN 'risks' THEN risk.risk_id
         WHEN 'issues' THEN issue.issue_id
         ELSE action.action_id
       END AS matched_node_id,
       $target AS matched_field,
       coalesce(action.status, '') AS semantic_status,
       coalesce(action.status_source, '') AS semantic_status_source,
       coalesce(action.status_confidence, '') AS semantic_status_confidence,
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

# 查詢追蹤關係：找出目前議案 FOLLOW_UP_OF 的前一筆議案。
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

# 查詢議題時間線：依 Issue 聚合所有 TRACKS_ISSUE 的議案，並帶出前後追蹤關係。
QUERY_ISSUE_TIMELINE = """
MATCH (issue:Issue)<-[:TRACKS_ISSUE]-(item:MeetingItem)<-[:HAS_ITEM]-(meeting:Meeting)
WHERE (
    $keyword = '' OR
    toUpper(coalesce(issue.title, '')) CONTAINS $keyword OR
    toUpper(coalesce(issue.signature, '')) CONTAINS $keyword OR
    toUpper(coalesce(item.content, '')) CONTAINS $keyword OR
    EXISTS {
      MATCH (item)-[:MENTIONS]->(keyword:Keyword)
      WHERE toUpper(keyword.name) CONTAINS $keyword
    } OR
    EXISTS {
      MATCH (item)-[:MENTIONS_PRODUCT]->(product:Product)
      WHERE toUpper(product.name) CONTAINS $keyword
    } OR
    EXISTS {
      MATCH (item)-[:MENTIONS_REGULATION]->(regulation:Regulation)
      WHERE toUpper(regulation.name) CONTAINS $keyword
    }
  )
OPTIONAL MATCH (item)-[:FOLLOW_UP_OF]->(previous:MeetingItem)
OPTIONAL MATCH (previous_meeting:Meeting)-[:HAS_ITEM]->(previous)
OPTIONAL MATCH (next:MeetingItem)-[:FOLLOW_UP_OF]->(item)
OPTIONAL MATCH (next_meeting:Meeting)-[:HAS_ITEM]->(next)
WITH issue, item, meeting, previous, previous_meeting, next, next_meeting,
     coalesce(issue.issue_id, issue.signature, issue.title, elementId(issue)) AS issue_id
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       issue_id AS issue_id,
       issue.title AS issue_title,
       issue.signature AS issue_signature,
       issue_id AS matched_node_id,
       issue.title AS matched_entity,
       'TRACKS_ISSUE' AS matched_relation,
       'issue_timeline' AS matched_field,
       previous.item_id AS previous_item_id,
       previous.content AS previous_content,
       previous_meeting.meeting_id AS previous_meeting_id,
       previous_meeting.meeting_name AS previous_meeting_name,
       next.item_id AS next_item_id,
       next.content AS next_content,
       next_meeting.meeting_id AS next_meeting_id,
       next_meeting.meeting_name AS next_meeting_name
ORDER BY issue_id ASC, meeting.meeting_date ASC, item.item_no ASC
LIMIT $limit
"""
