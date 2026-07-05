# 論文修改紀錄

本文檔用於統一記錄論文後續調整內容，包含修改頁次、修改位置、調整原因與修改說明。

## 2026-06-27

| 頁次 | 修改位置 | 調整說明 |
|---|---|---|
| 摘要頁 | 中文摘要 | 依老師建議，摘要需補強研究成果與比較結果，不只說明系統做法。建議加入資料規模、GraphRAG 問答結果，以及與 Vector-RAG 比較後的差異。 |
| Abstract 頁 | 英文摘要 | 中文摘要調整後需同步修改英文摘要，使中英文內容一致，並補上資料規模、問答測試結果與 Vector-RAG 比較結果。 |
| 11 頁 | 2.3 文件結構解析、表格辨識與欄位抽取 | 第二段內容出現「涵蓋 格模型」，調整為「涵蓋表格模型」。 |

### 摘要調整重點

1. 保留研究問題：企業會議記錄以 PDF 分散保存，傳統全文檢索難以回答責任、時程、產品或法規關聯與來源回溯問題。
2. 修正方法描述：改以 Document、Meeting、MeetingItem 三層資料、MongoDB、Neo4j、Qdrant 與 GraphRAG 問答流程為主。
3. 刪除或弱化「結構感知排序、欄位權重、任務狀態分數」等後續實驗未作為主軸驗證的描述。
4. 補上實驗成果：9 份去識別化會議記錄、116 筆 MeetingItem、893 個節點、4,946 筆關係、116 筆向量索引。
5. 補上問答結果：18 題 GraphRAG 測試中，18 題正確、0 題部分正確、0 題錯誤或未充分回答。
6. 補上比較結果：相較於 Vector-RAG，GraphRAG 在責任歸屬、時程狀態與產品或法規關聯等需要結構化關係判斷的問題中較穩定。

### 建議替換內容：中文摘要

企業內部會議記錄保存專案決策、責任分派、產品開發進度、測試要求與追蹤結果等資訊，實務上卻常以 PDF 文件分散保存，導致後續查詢多依賴人工翻找或關鍵字比對。傳統全文檢索雖能找出包含查詢詞的文件，卻難以判斷該詞對應的會議項目、負責人、日期、追蹤狀態，以及其與產品或法規之間的關聯，也不易提供可回溯的回答來源。

針對上述問題，本研究以企業會議記錄為例，建構一套結合結構化文件解析、知識圖譜與向量檢索之 GraphRAG 檢索系統。系統將會議記錄 PDF 解析為 Document、Meeting 與 MeetingItem 三層資料，並同步建立 MongoDB 結構化資料、Neo4j 知識圖譜與 Qdrant 向量索引。使用者提出問題後，系統依問題類型結合圖譜關係查詢、向量語意召回與結構化欄位回查，組裝具來源依據的證據集合，再由語言模型產生受來源限制的回答。

實驗結果顯示，本研究系統成功將 9 份去識別化會議記錄建立為 9 筆會議資料與 116 筆會議項目，並建構 893 個知識圖譜節點、4,946 筆圖譜關係與 116 筆向量索引。在 18 題 GraphRAG 問答測試中，系統取得 18 題正確、0 題部分正確、0 題錯誤或未充分回答；與純向量 RAG 比較，GraphRAG 在責任歸屬、時程狀態與產品或法規關聯等需要結構化關係判斷的問題中表現較穩定。整體而言，本研究證明 GraphRAG 可將企業會議記錄轉換為可查詢、可關聯且可回溯的知識資源，提升企業內部會議資料檢索與決策追蹤之可用性。

關鍵詞：文件結構解析、知識圖譜、GraphRAG、向量檢索

## 2026-06-29

| 頁次 | 修改位置 | 調整說明 |
|---|---|---|
| 第四章 | 4.3.2 結構化資料建立 | 依老師建議，補充 MongoDB collection schema。圖 4.2 保留作為 Document、Meeting、MeetingItem 三層資料模型示意圖，另以表格列出資料模型實際欄位、型別與用途。 |
| 第四章 | 4.6 GraphRAG 問答流程 | 依老師建議，補充 GraphRAG 問答流程循序圖，用於呈現使用者、前端介面、Django 後端、查詢路由、Neo4j、Qdrant、MongoDB 與 Ollama 之間的互動順序。 |

### 4.3.2 結構化資料建立補充重點

1. 說明圖 4.2 為概念層級的資料模型關係圖，呈現 Document、Meeting 與 MeetingItem 三層結構。
2. 補充 MongoDB 中三個主要 collection 與資料模型的對應關係：`documents` 對應 Document、`meeting_minutes` 對應 Meeting、`meeting_items` 對應 MeetingItem。
3. 在 4.3.2 加入 collection schema 表格，僅列出圖 4.2 資料模型中已有的欄位，避免與實作中額外輔助欄位混在一起。
4. 建議表名使用中文，例如「表 4.X MongoDB 結構化資料模型欄位說明」，欄位名稱保留英文，以維持與系統實作一致。

### 建議新增內容：4.3.2 結構化資料建立

本研究於 MongoDB 中建立三個主要 collection，分別為 `documents`、`meeting_minutes` 與 `meeting_items`，對應至資料模型中的文件（Document）、會議（Meeting）與會議項目（MeetingItem）三個層級。其中，文件層保存上傳文件之基本資訊與處理狀態；會議層保存由會議記錄解析而得的會議基本資料；會議項目層則保存每一筆追蹤事項或決議項目的內容、負責人、日期與追蹤結果。三層資料透過 `document_id` 與 `meeting_id` 維持關聯，使系統能由原始文件追溯至會議資料，並進一步定位至具體會議項目。

**表 4.X MongoDB 結構化資料模型欄位說明**

| 資料模型 | 欄位名稱 | 資料型別 | 說明 |
|---|---|---|---|
| 文件（Document） | document_id | String | 文件唯一識別碼 |
| 文件（Document） | original_filename | String | 原始檔案名稱 |
| 文件（Document） | doc_type | String | 文件類型 |
| 文件（Document） | file_path | String | 文件儲存路徑 |
| 文件（Document） | upload_status | String | 文件上傳或處理狀態 |
| 文件（Document） | created_at | DateTime | 文件建立時間 |
| 文件（Document） | page_count | Number | 文件頁數 |
| 會議（Meeting） | meeting_id | String | 會議唯一識別碼 |
| 會議（Meeting） | document_id | String | 對應文件層的文件識別碼 |
| 會議（Meeting） | meeting_name | String | 會議名稱 |
| 會議（Meeting） | meeting_date | String | 會議日期 |
| 會議（Meeting） | location | String | 會議地點 |
| 會議（Meeting） | chairperson | String | 主席 |
| 會議（Meeting） | recorder | String | 記錄人員 |
| 會議（Meeting） | responsible_unit | String | 權責單位 |
| 會議（Meeting） | attendees | Array<String> | 出席人員 |
| 會議項目（MeetingItem） | item_id | String | 會議項目唯一識別碼 |
| 會議項目（MeetingItem） | meeting_id | String | 對應會議層的會議識別碼 |
| 會議項目（MeetingItem） | document_id | String | 對應文件層的文件識別碼 |
| 會議項目（MeetingItem） | item_no | String | 會議項次 |
| 會議項目（MeetingItem） | content | String | 會議項目內容 |
| 會議項目（MeetingItem） | owner | String | 負責人或負責單位 |
| 會議項目（MeetingItem） | planned_date | String | 預計完成日期 |
| 會議項目（MeetingItem） | actual_completed_date | String | 實際完成日期 |
| 會議項目（MeetingItem） | tracking_result | String | 追蹤結果 |
| 會議項目（MeetingItem） | status | String | 會議項目處理狀態 |

### 4.6 GraphRAG 問答流程補充重點

1. 在 4.6 加入循序圖，建議圖名為「圖 4.X GraphRAG 問答流程循序圖」。
2. 循序圖呈現使用者送出問題後，系統依序經過前端介面、Django 後端、查詢路由、Neo4j、Qdrant、MongoDB 與 Ollama 的互動流程。
3. 圖中區分「需要圖譜關係」與「需要語意召回」兩種查詢情境，說明 GraphRAG 會依問題類型選擇圖譜查詢、向量查詢或兩者整合。
4. 修正圖中 Qdrant 回傳說明：向量語意查詢會回傳相似 `item_id` 與分數，後續再依 `meeting_id` / `item_id` 回查 MongoDB 取得完整結構化欄位。

### 建議新增內容：4.6 GraphRAG 問答流程

為說明使用者提出問題後，系統各模組之間的互動順序，本研究以循序圖呈現 GraphRAG 問答流程，如圖 4.X 所示。使用者於前端介面輸入問題後，Django 後端會先進行問題理解與查詢路由判斷，再依問題類型查詢 Neo4j 知識圖譜或 Qdrant 向量索引，取得候選 `meeting_id` 或 `item_id`。接著，系統回查 MongoDB 取得完整結構化欄位，整理為來源證據集合後，交由 Ollama 語言模型產生受證據限制的回答，最後將答案與來源依據回傳給使用者。

**圖 4.X GraphRAG 問答流程循序圖**

## 2026-06-30

| 頁次 | 修改位置 | 調整說明 |
|---|---|---|
| 第五章 | 圖 5.2 至圖 5.7 GraphRAG 問答畫面 | 依老師建議，補強各查詢結果圖的可讀性。每張圖下方應補充查詢結果來源 ID 對照表，列出 `evidence_id`、`meeting_id`、`item_id`、`item_no` 與會議項目內容，避免讀者只看到 ID 而無法理解節點代表的實際會議項目。 |
| 第五章 | 圖 5.4 關鍵詞探索型 GraphRAG 問答畫面 | 將代表題調整為「提及 Taper length 相關的會議項目有哪些？」。此題來源較集中，適合呈現關鍵詞探索型查詢如何由查詢詞回溯至具體 MeetingItem。 |
| 第五章 | 圖 5.6 開放模糊型 GraphRAG 問答畫面 | 針對截圖可讀性不足問題，建議不要放完整系統畫面；可拆成「回答與來源證據」及「圖譜關係視覺化」兩張子圖，或裁切右側圖譜空白區並放大節點群。圖下再以來源 ID 對照表補足節點內容。 |
| 第四章 | 4.4.3 知識圖譜關係查詢 | 依老師建議，補充 Neo4j / Cypher 查詢範例，說明系統如何由使用者問題轉換為圖譜關係查詢，並回傳 meeting_id、item_id、item_no 與會議項目內容。 |

### 圖 5.2 至圖 5.7 補強原則

1. 圖片本身只呈現系統介面與圖譜關係，不要求讀者從小圖中讀完整 ID 與內容。
2. 圖下方加入正式表格，表名可寫為「表 5.X 圖 5.X 查詢結果來源 ID 對照表」，並標註「資料來源：本研究整理」。
3. 正文需引用表格，例如「各 item_id 對應之會議內容如表 5.X 所示」。
4. 若查詢結果過多，正文只列代表性項目或唯一命中項目，完整來源清單可移至附錄，避免表格過長影響閱讀。
5. 截圖建議使用高解析度或瀏覽器放大後重新截圖，並裁切無關空白、工具列與過寬畫布，使回答區、來源證據與高亮節點成為第一視覺重點。

### 建議新增內容：圖 5.4 關鍵詞探索型查詢

查詢問題：提及 Taper length 相關的會議項目有哪些？

圖 5.4 顯示關鍵詞探索型問題的查詢結果。系統以「Taper length」作為查詢關鍵詞，從會議項目內容中找出直接提及該詞的來源項目。查詢結果顯示，系統可定位到 item_no 02 的會議項目，其內容為「Taper length 確定為 10mm」。此結果證明 GraphRAG 可將關鍵詞查詢回溯至具體 MeetingItem，而不是只回傳文件層級或泛泛的摘要結果。其來源 ID 對照如表 5.X 所示。

**表 5.X 圖 5.4 查詢結果來源 ID 對照表**

資料來源：本研究整理

| evidence_id | meeting_id | item_id | item_no | 會議項目內容 |
|---|---|---|---|---|
| evidence_001 | meeting_523b2503e014 | item_4437863f2db3 | 02 | Taper length 確定為 10mm。 |

### 建議新增內容：圖 5.6 圖片呈現調整

圖 5.6 顯示開放模糊型問題的查詢結果。系統針對「P1812 Coformity stem 會議進度與會議摘要」進行查詢，先定位 P1812 Coformity stem 器械進度會議，再彙整該會議下的 4 筆 MeetingItem。圖中右側圖譜顯示會議節點與會議項目節點之間的 HAS_ITEM 關係；各 item_id 對應之會議內容如表 5.X 所示。

圖 5.6 的截圖建議拆成兩張子圖：圖 5.6(a) 保留左側回答區與來源依據，圖 5.6(b) 保留右側圖譜節點與 HAS_ITEM 關係。若仍使用單張圖，應裁掉多餘工具列與右側黑色空白，並放大節點群，使中心會議節點與 4 個 MeetingItem 節點可辨識。

### 建議新增內容：4.4.3 知識圖譜關係查詢範例

為使讀者理解圖譜關係如何被查詢，建議於 4.4.3 加入一段 Cypher 查詢範例。本文不需列出所有系統查詢，只需列出與第五章代表問題對應的 3 至 4 個範例，呈現「使用者問題、使用關係、Cypher 查詢、回傳欄位」之間的對應關係。

系統於 Neo4j 中以 `Document`、`Meeting`、`MeetingItem`、`Person`、`Date`、`Product`、`Regulation` 與 `Keyword` 等節點表示會議記錄資料，並以 `HAS_MEETING`、`HAS_ITEM`、`RESPONSIBLE_BY`、`HAS_PLANNED_DATE`、`MENTIONS_PRODUCT`、`MENTIONS_REGULATION` 等關係表示來源層級、責任歸屬、日期與內容提及關係。使用者提出問題後，系統會先判斷問題類型，再選擇對應的 Cypher 查詢取得候選 `MeetingItem`，最後回查 MongoDB 取得完整欄位並組成 GraphRAG 回答。

**表 4.X GraphRAG 圖譜關係查詢範例**

資料來源：本研究整理

| 查詢目的 | 使用者問題範例 | 主要圖譜關係 | 回傳重點 |
|---|---|---|---|
| 責任歸屬查詢 | Person_F03E4ECA0A 負責哪些項目？ | `RESPONSIBLE_BY`、`HAS_ITEM` | 找出該人負責的 MeetingItem |
| 預計日期查詢 | 2017 年 12 月 15 日要完成哪些事項？ | `HAS_PLANNED_DATE`、`HAS_ITEM` | 找出預計日期符合條件的 MeetingItem |
| 產品或關鍵詞關聯查詢 | stem 相關的會議項目有哪些？ | `MENTIONS_PRODUCT`、`MENTIONS`、`HAS_ITEM` | 找出提及產品或關鍵詞的 MeetingItem |
| 會議項目展開 | P1812 Coformity stem 會議進度與會議摘要 | `HAS_ITEM` | 依會議節點展開其所有 MeetingItem |

責任歸屬型問題可使用 `RESPONSIBLE_BY` 關係查詢負責人對應的會議項目，例如：

```cypher
MATCH (item:MeetingItem)-[:RESPONSIBLE_BY]->(person:Person)
WHERE toUpper(person.name) CONTAINS toUpper($person_name)
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       person.name AS matched_person
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
```

時程狀態型問題可使用 `HAS_PLANNED_DATE` 關係查詢特定預計完成日期的會議項目，例如：

```cypher
MATCH (item:MeetingItem)-[:HAS_PLANNED_DATE]->(date:Date)
WHERE date.date_value = $planned_date
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       date.date_value AS planned_date
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
```

關鍵詞或產品探索型問題可查詢 `MENTIONS_PRODUCT` 或 `MENTIONS` 關係，並回傳對應的會議項目。例如查詢 stem 相關項目時，可使用下列查詢：

```cypher
MATCH (item:MeetingItem)-[:MENTIONS_PRODUCT]->(product:Product)
WHERE toUpper(product.name) CONTAINS toUpper($product_name)
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       product.name AS matched_product
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
```

若查詢詞為較細的內容片語，例如「Taper length」，系統亦可在候選會議項目內容中進行片語比對，將命中項目回傳為來源證據：

```cypher
MATCH (meeting:Meeting)-[:HAS_ITEM]->(item:MeetingItem)
WHERE toUpper(item.content) CONTAINS toUpper($keyword)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content,
       $keyword AS matched_keyword
ORDER BY meeting.meeting_date DESC, item.item_no ASC
LIMIT $limit
```

會議摘要或會議進度查詢則可先定位 `Meeting` 節點，再透過 `HAS_ITEM` 展開該會議下的所有會議項目：

```cypher
MATCH (meeting:Meeting)
WHERE toUpper(meeting.meeting_name) CONTAINS toUpper($meeting_hint)
MATCH (meeting)-[:HAS_ITEM]->(item:MeetingItem)
RETURN meeting.meeting_id AS meeting_id,
       meeting.meeting_name AS meeting_name,
       meeting.meeting_date AS meeting_date,
       item.item_id AS item_id,
       item.item_no AS item_no,
       item.content AS content
ORDER BY item.item_no ASC
LIMIT $limit
```

上述查詢範例顯示，GraphRAG 並非只依語意相似度召回文字，而是會依問題目的選擇明確的圖譜關係。查詢結果保留 `meeting_id`、`item_id` 與 `item_no`，因此後續回答可回溯至具體會議項目，並能與第五章圖 5.2 至圖 5.7 的來源 ID 對照表相互驗證。

## 2026-06-30 補充調整紀錄

| 章節/位置 | 調整內容 | 調整理由 |
|---|---|---|
| 3.6.2 關鍵詞、產品與法規抽取方法 | 補充語言模型輔助候選詞抽取機制，說明系統在設定啟用時會以 JSON 格式取得候選關鍵詞、詞彙類型與分數，且結果需經停用詞排除、正規化、去重與排序後才寫入 Keyword、Product 或 Regulation 節點。 | 目前系統實際啟用 LLM 輔助關鍵詞抽取，方法章需與實作一致；同時強調 LLM 為輔助候選詞來源，不直接等同最終標註或正式事實。 |
| 2.8 知識圖譜與關聯查詢 | 補充知識圖譜建構中的知識擷取文獻脈絡，加入 TextRank、命名實體辨識、知識圖譜知識擷取與 LLM 結構化資訊抽取相關文獻。 | 支撐 3.6.2 中關鍵詞、產品與法規節點由文字欄位抽取的設計，並避免將 LLM 抽取描述為無文獻依據的實作細節。 |
| 參考文獻 | 新增 [26] Mihalcea & Tarau (2004)、[27] Nadeau & Sekine (2007)、[28] Ji et al. (2022)、[29] Dagdelen et al. (2024)。 | 補足關鍵詞抽取、實體辨識、知識圖譜建構與 LLM 結構化資訊抽取之文獻來源，且來源皆為可查證文獻。 |
| 5.2 實驗資料與系統設定 | 新增 5.2.1 系統處理時間紀錄，並以紅字表格整理文件前處理與結構化解析、知識圖譜建構、GraphRAG 查詢回應之處理時間。 | 回應老師要求補充前處理時間、知識圖譜建構時間與查詢回應時間，並將其定位為第 5 章實驗結果與分析中的系統執行成本觀察。 |
| 5.2.1 系統處理時間紀錄 | 最終表格僅保留「知識圖譜建構」完整時間，不再將核心建構與完整建構並列於主表。知識圖譜建構時間定義為包含規則式抽取、jieba 中文關鍵詞抽取、LLM 輔助候選詞抽取、產品與法規節點建立，以及 Neo4j 節點與關係寫入。 | 使用者與委員較容易理解「系統實際建構圖譜所需時間」；避免同時列出核心建構與完整建構造成到底哪個才是建構時間的疑問。 |
| 5.2.1 系統處理時間紀錄 | 表格採用三列主要處理階段：文件前處理與結構化解析、知識圖譜建構、GraphRAG 查詢回應。 | 讓表格更簡潔，直接對應老師提出的三項時間紀錄需求。 |
| 第 5 章實驗評估與附錄 | 補充 GraphRAG 問答評估判定標準，明確定義「正確」、「部分正確」、「錯誤／未充分回答」之判斷依據，並整理部分正確或錯誤案例的具體內容。評估表由原本僅統計題數，調整為同時呈現資料集中應找回項目數、系統找回項目數與正確找回項目數；若逐題內容過多，移至附錄呈現。 | 回應老師對評估可信度的疑問，避免只用「3 題中幾題正確」描述結果，改以來源項目層級檢查系統是否真正找回應有 MeetingItem，讓正確、部分正確與錯誤判定更可驗證。 |

### 系統處理時間表格最終採用數值

| 處理階段 | 量測範圍 | 資料量 | 處理時間 |
|---|---|---:|---:|
| 文件前處理與結構化解析 | PDF 文字抽取、會議欄位解析、MeetingItem 切分與去識別化轉換 | 10 份 PDF | 總計 6.7320 秒；平均 0.6732 秒/份 |
| 知識圖譜建構 | 規則式抽取、jieba 中文關鍵詞抽取、LLM 輔助候選詞抽取、產品與法規節點建立，以及 Neo4j 節點與關係寫入 | 9 份會議、116 筆 MeetingItem | 3112.2781 秒，約 51 分 52 秒 |
| GraphRAG 查詢回應 | 問題路由、證據檢索、上下文組裝、證據選擇與 Ollama 回答生成 | 18 題測試問題 | 總計 518.8093 秒；平均 28.8227 秒/題；中位數 25.1155 秒 |
