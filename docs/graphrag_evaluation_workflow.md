# GraphRAG 評估流程操作記錄

本文記錄 GraphRAG 問答穩定度檢查流程。目的不是新增使用者功能，而是建立回歸測試機制，避免後續修改造成「原本答對的問題變錯」、「答案和圖譜不一致」、「來源證據不一致」。

## 核心概念

目前 GraphRAG 問答流程已改成：

```text
User Question
-> EvidenceSet
-> Claims
-> Verified Answer
-> Graph View
-> Sources
```

也就是最終答案、圖譜視圖、sources 都應該來自同一批 `evidence_id`。

評估流程會檢查：

- answer 是否包含 expected item_id
- answer 是否出現不該出現的 item_id
- graph paths 是否包含 expected relation
- graph paths、sources、answer claims 的 `evidence_id` 是否一致
- 找不到資料時是否正確回傳 insufficient

## 相關檔案

- `apps/graphrag/evaluation.py`
  - GraphRAG golden case 載入、產生、評估邏輯

- `apps/graphrag/management/commands/eval_graphrag.py`
  - 執行 golden case 評估

- `apps/graphrag/management/commands/seed_graphrag_cases.py`
  - 從問題清單自動產生候選 golden cases

- `apps/graphrag/fixtures/graphrag_seed_questions.txt`
  - 問題清單，一行一題

- `apps/graphrag/fixtures/graphrag_golden_cases.json`
  - 手動維護的 golden cases

## 一次性產生候選 Golden Cases

可以用網頁操作，也可以用 command line 操作。

### 方法一：GraphRAG 頁面操作

進入 GraphRAG 頁面後：

1. 點右上角「進階」。
2. 找到「回歸評估」區塊。
3. 在文字框輸入問題，一行一題。
4. 點「產生候選」。
5. 檢查每題顯示的：
   - expected items
   - expected meetings
   - expected relations
   - observed answer
   - evidence consistency
6. 確認某題正確後，勾選該題。
7. 點「保存已確認」，系統會把已勾選的 cases merge 到 golden cases 檔案。
8. 點「執行評估」可以直接用目前候選 cases 跑一次 pass/fail。

保存規則：

- 只保存已勾選確認的 cases。
- 保存時會設為 `enabled: true` 與 `review_status: approved`。
- 使用 case `id` merge，不會清空既有 golden cases。
- 未勾選的 `needs_review` cases 不會保存。

### 方法二：Command Line 操作

先編輯問題清單：

```text
apps/graphrag/fixtures/graphrag_seed_questions.txt
```

一行放一個問題，例如：

```text
陳聖昌負責哪些項目
2017 年 12 月 15 日要完成哪些事項
P1812 Coformity stem器械進度 會議包含哪些事項
```

執行自動產生候選 cases：

```bash
uv run python manage.py seed_graphrag_cases --questions apps/graphrag/fixtures/graphrag_seed_questions.txt --out apps/graphrag/fixtures/graphrag_golden_cases.generated.json
```

這個指令會實際呼叫目前 GraphRAG 問答，並根據回傳結果產生：

- `expected_item_ids`
- `expected_meeting_ids`
- `expected_relations`
- `observed.answer`
- `observed.route`
- `observed.evidence_consistency`

預設產生的 case 會是：

```json
"enabled": false,
"review_status": "needs_review"
```

這是刻意設計。不要直接把自動產生的結果當標準答案，必須先人工確認。

## 人工審查 Golden Cases

打開：

```text
apps/graphrag/fixtures/graphrag_golden_cases.generated.json
```

逐題確認：

- `question` 是否是要固定檢查的問題
- `expected_item_ids` 是否正確且完整
- `expected_meeting_ids` 是否正確
- `expected_relations` 是否符合問題類型
- `unexpected_item_ids` 是否需要補上不該出現的項目
- `observed.answer` 是否合理

確認正確後，把該 case 改成：

```json
"enabled": true,
"review_status": "approved"
```

如果該題目前系統答錯，不要 enable。可以保留：

```json
"enabled": false,
"review_status": "known_failure"
```

## 執行評估

執行預設 golden cases：

```bash
uv run python manage.py eval_graphrag
```

執行指定 cases 檔案：

```bash
uv run python manage.py eval_graphrag --cases apps/graphrag/fixtures/graphrag_golden_cases.generated.json
```

輸出完整 JSON 報告：

```bash
uv run python manage.py eval_graphrag --cases apps/graphrag/fixtures/graphrag_golden_cases.generated.json --json
```

如果 cases 全部 disabled，允許成功結束：

```bash
uv run python manage.py eval_graphrag --allow-empty
```

## 日常修改後的檢查流程

每次修改 GraphRAG、Neo4j 查詢、query router、prompt、圖譜視覺化後，建議依序執行：

```bash
uv run python manage.py test apps.graphrag apps.graph
uv run python manage.py eval_graphrag --cases apps/graphrag/fixtures/graphrag_golden_cases.generated.json
uv run python manage.py test
```

如果有改前端：

```bash
node --check static/js/graphrag-page.js
```

## 評估失敗時怎麼看

常見失敗訊息：

```text
answer missing expected item_id: item_xxx
```

代表文字答案沒有包含應出現的 item。

```text
graph missing expected item_id: item_xxx
```

代表圖譜沒有畫出應出現的 item。

```text
sources missing expected item_id: item_xxx
```

代表 sources 沒有包含應出現的 item。

```text
graph evidence_ids do not match answer claim evidence_ids
```

代表答案和圖譜使用的 evidence 不一致，這是高優先級問題。

```text
source evidence_ids do not match answer claim evidence_ids
```

代表答案和 sources 使用的 evidence 不一致，也屬於高優先級問題。

## 建議維護規則

- Golden case 只放已人工確認正確的問題。
- 不要因為評估失敗就直接改 expected ids，先確認是系統錯還是標準答案錯。
- 明確查詢題要優先加入 golden cases，例如：
  - 某人負責哪些項目
  - 某日期要完成哪些事項
  - 某會議包含哪些事項
  - 某產品相關事項
  - 某法規相關事項
- 每次修正一個使用者回報問題，就補一題 golden case。

## 最小操作範例

```bash
uv run python manage.py seed_graphrag_cases --questions apps/graphrag/fixtures/graphrag_seed_questions.txt --out apps/graphrag/fixtures/graphrag_golden_cases.generated.json
```

人工審查並把可信 cases 改成：

```json
"enabled": true
```

再執行：

```bash
uv run python manage.py eval_graphrag --cases apps/graphrag/fixtures/graphrag_golden_cases.generated.json
```
