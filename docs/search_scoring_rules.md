# 搜尋分數規則

本文件整理目前會議記錄搜尋系統的分數規則。

主要實作位置：

- `apps/search/ranking.py`
- `apps/search/feedback.py`
- `apps/graph/graph_search.py`
- `apps/search/services.py`

## 最終分數

搜尋結果目前採用加總制：

```text
final_score =
  keyword_score
+ structure_score
+ task_score
+ recency_score
+ feedback_score
+ graph_score
```

會議層級的結果會彙總：

- 會議基本資料的命中分數。
- 命中的會議項目分數。
- 近期分數。
- 歷史點擊回饋分數。
- Neo4j 可用時的圖譜關鍵字分數。

會議項目層級的分數為：

```text
item_final_score =
  keyword_score
+ structure_score
+ task_score
+ feedback_score
+ graph_score
```

## 關鍵字分數

`keyword_score` 會在查詢關鍵字命中特定欄位時加分。

### 會議欄位

| 欄位 | 分數 |
| --- | ---: |
| `meeting_name` | 10 |
| `responsible_unit` | 5 |
| `chairperson` | 4 |
| `recorder` | 3 |
| `attendees` | 3 |
| `location` | 2 |

### 會議項目欄位

| 欄位 | 分數 |
| --- | ---: |
| `content` | 8 |
| `owner` | 5 |
| `tracking_result` | 4 |
| `planned_date` | 3 |
| `actual_completed_date` | 3 |

如果同一場會議底下有多個會議項目命中查詢關鍵字，這些 item 的關鍵字分數會加總到該會議結果。

## 結構分數

`structure_score` 是額外加權，用來提高命中重要欄位的結果排序。

| 欄位 | 分數 |
| --- | ---: |
| `meeting_name` | 5 |
| `content` | 4 |
| `owner` | 3 |
| `responsible_unit` | 3 |
| `attendees` | 2 |

範例：如果查詢關鍵字命中 `meeting_name`，該結果會同時獲得：

```text
keyword_score +10
structure_score +5
```

## 任務分數

`task_score` 只套用在會議項目，用來提高「看起來需要追蹤或處理」的項目排序。

| 條件 | 分數 |
| --- | ---: |
| 有 `owner` | 2 |
| 有 `planned_date` | 2 |
| 沒有 `actual_completed_date` | 2 |
| 沒有 `tracking_result` | 1 |

單一 item 的任務分數最高為 `7`。

以下 owner 值會被視為空值：

```text
"", "--", "na", "n/a", "none", "null"
```

## 近期分數

`recency_score` 依據會議日期 `meeting_date` 計算，套用在會議層級。

| 會議距今天數 | 分數 |
| --- | ---: |
| 0-30 天 | 5 |
| 31-90 天 | 3 |
| 91-180 天 | 1 |
| 超過 180 天 | 0 |
| 日期缺失或格式錯誤 | 0 |

如果會議日期是未來日期，系統會當作距今天數為 `0`，因此會得到 `5` 分。

## 回饋分數

`feedback_score` 來自歷史搜尋點擊紀錄。

### 會議回饋分數

```text
meeting_feedback_score =
  全站點擊該 meeting 次數 * 0.5
+ 相似查詢下點擊該 meeting 次數 * 0.5
```

### 會議項目回饋分數

```text
item_feedback_score =
  全站點擊該 item 次數 * 1.0
+ 相似查詢下點擊該 item 次數 * 0.5
```

查詢會在以下任一條件成立時被視為相似：

- 正規化後完全相同。
- 其中一個查詢字串包含另一個查詢字串。
- token 重疊比例至少為 `0.5`。

正規化會將查詢轉成小寫，並壓縮多餘空白。

## 圖譜分數

`graph_score` 會在 Neo4j 圖譜搜尋可用時套用。

圖譜搜尋會先用原始查詢找出相關關鍵字，再搜尋與這些關鍵字相連的會議項目。

| 圖譜命中類型 | 分數 |
| --- | ---: |
| 直接命中原始查詢關鍵字 | 3.0 |
| 命中相關關鍵字 | `max(related_weight * 2.5, 0.5)` |

如果同一個 meeting 或 item 有多個圖譜命中，圖譜分數會累加。

## 查詢比對規則

所有比對都不區分大小寫。

ASCII 查詢會使用類似字詞邊界的正則比對：

```text
(?<![a-z0-9])query(?![a-z0-9])
```

這可以避免像 `FDA` 這類關鍵字誤命中到較長英數字串的中間。

非 ASCII 查詢使用 substring 包含判斷。

陣列欄位，例如 `attendees`，只要其中任一元素命中查詢就算命中。

## 命中欄位輸出

API 會在每筆搜尋結果中回傳命中欄位資訊：

- `matched_fields`：命中的欄位清單，會去除重複欄位。
- `matched_snippets`：部分欄位的高亮片段。
- `matched_items`：命中的會議項目，內含各自的 `score_detail`。

目前會產生 snippet 的欄位：

```text
meeting_name
responsible_unit
content
owner
tracking_result
```

注意：`matched_fields` 目前是會議搜尋結果層級的彙總資訊。它可以表示這筆結果有哪些欄位命中，但還不是完整的「每個關鍵字、每個欄位、每個 item」明細。

## 篩選與納入規則

當有查詢關鍵字時：

- 如果會議結果的 `final_score` 小於或等於 `0`，該結果會被排除。
- 如果 item 沒有關鍵字分數、沒有圖譜分數、沒有 owner 篩選，且沒有啟用 item 狀態篩選，該 item 會被排除。

當沒有查詢關鍵字，也沒有 item 篩選時：

- 會議結果仍可被列出。
- `matched_items` 會被清空。

## 排序規則

預設依照最高 `final_score` 排序。

目前支援的排序模式：

| 排序模式 | 行為 |
| --- | --- |
| `final_score` | 最終分數高者優先 |
| `keyword_score` | 關鍵字分數高者優先 |
| `feedback_score` | 回饋分數高者優先 |
| `graph_score` | 圖譜分數高者優先 |
| `meeting_date_asc` | 會議日期較舊者優先 |
| `meeting_date_desc` | 會議日期較新者優先 |

同分時通常會再依最終分數、會議日期與 `meeting_id` 排序。
