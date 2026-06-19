# GraphRAG Retrieval Modes

本系統採 hybrid GraphRAG。問題不直接交給單一路徑處理，而是先分類成 retrieval mode，再建立 canonical evidence set。答案與圖譜都只能使用同一批 evidence。

## Core Modes

| Query type | 適用問題 | 主要資料來源 | 回答策略 | 圖譜視圖 |
| --- | --- | --- | --- | --- |
| `structural_list` | 某會議包含哪些事項、列出討論項目 | Neo4j `Meeting-[:HAS_ITEM]->MeetingItem`，Mongo fallback | 完整列出符合會議的事項 | 畫該會議與所有回答事項 |
| `relation_lookup` | 誰負責、日期、單位、人員角色 | Neo4j whitelist relation query | 只回答明確關係 evidence | 畫實際關係，例如 `RESPONSIBLE_BY`、`HAS_PLANNED_DATE` |
| `composite_query` | 人 + 產品 + 法規 + 狀態混合查詢 | Neo4j whitelist composite query | 依條件過濾 action/decision/risk/issue evidence | 畫回答使用的條件關係 |
| `meeting_summary` | 某次會議摘要、重點整理 | 指定會議完整 items + semantic/vector 輔助 | LLM 綜整 evidence claims，不逐項硬列 | 畫摘要實際引用的會議事項 |
| `semantic_summary` | 風險、決議、問題、追蹤整理 | semantic/vector + Neo4j semantic nodes + keyword fallback | LLM 做跨 evidence 摘要 | 畫回答引用的 semantic evidence |
| `follow_up_tracking` | 跨會議追蹤、後續狀況、問題演變 | Neo4j `Issue<-[:TRACKS_ISSUE]-MeetingItem` + `FOLLOW_UP_OF` | 依 issue 分組並按 timeline 整理 | 畫回答引用的 issue timeline evidence |
| `keyword_exploration` | 某產品/法規/關鍵詞相關內容 | keyword graph + vector + Mongo fallback | 整理相關 evidence | 畫回答引用的 keyword/product/regulation evidence |
| `open_qa` | 無法明確分類的開放問題 | hybrid retrieval | evidence-grounded answer | 畫回答引用 evidence |

## Design Rules

- LLM 可以負責摘要、措辭與 claim 組織，但不能直接決定事實。
- 精確查詢優先走 deterministic graph relation，不依賴 LLM 猜查詢。
- 會議摘要不是 keyword search summary；必須先鎖定會議並取完整 meeting items。
- `contexts.graph` 是回答證據圖，不是 Neo4j 隨機子圖。
- Golden cases 必須同時檢查 answer、sources、graph evidence 是否一致。

## Current Priority

目前已正式支援：

- `structural_list`
- `relation_lookup`
- `composite_query`
- `meeting_summary`
- `semantic_summary`：已支援風險與決議類語意整理，優先使用 `HAS_RISK` / `HAS_DECISION` 等圖關係 evidence。
- `follow_up_tracking`：已支援跨會議 issue/follow-up 演變追蹤，優先使用 `TRACKS_ISSUE` / `FOLLOW_UP_OF` evidence。

下一階段應補強：

- 產品片語查詢精準化，例如 `提及 Corail stem 的會議` 不應降級成 `stem`。

## Known Issues To Track

### Product Phrase Query Over-Expansion

- Case: `提及 Corail stem 的會議`
- Observed behavior: query planner extracts `product_name = stem` instead of the full product phrase `Corail stem`.
- Impact: Neo4j product relation lookup uses case-insensitive `CONTAINS`, so the graph can include unrelated products or meetings that mention other `stem` products, such as `Conformity stem` or `cemented stem`.
- Expected behavior: preserve multi-word product phrases as exact query entities first, then fall back to partial matching only when no exact phrase match exists.
- Required follow-up:
  - Improve product entity extraction for English/mixed product phrases.
  - Prefer exact/phrase match for `MENTIONS_PRODUCT`.
  - Disable broad keyword fallback for explicit product mention questions unless exact graph retrieval returns no evidence.
  - Add a golden case for `提及 Corail stem 的會議` to ensure answer evidence and graph evidence only contain direct `Corail stem` matches.

## Text2Cypher Exploration

Text2Cypher is available only as an Advanced exploration tool. It is intentionally not part of `/api/graphrag/ask/`.

Rules:

- It generates read-only Cypher for graph exploration.
- It does not generate the final GraphRAG answer.
- Results are not merged into the canonical EvidenceSet.
- The prompt includes an enhanced schema context with labels, properties, and common graph patterns.
- The prompt includes few-shot question/Cypher examples for common meeting-record graph exploration.
- Common low-complexity exploration questions can use prewritten example templates before calling the LLM.
- Guardrails block write operations such as `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`, `DROP`, `CALL`, `LOAD`, and APOC calls.
- Queries are limited to whitelisted labels and relationships.
- A bounded `LIMIT` is always enforced before execution.
- The table shows the raw Text2Cypher rows.
- The shared graph workspace renders a deterministic graph projection from those rows.
- For non-aggregation questions, Text2Cypher should return `path` plus scalar fields.
- The graph renderer prefers explicit Neo4j paths and only draws relationships contained in returned paths.
- If Text2Cypher returns isolated nodes only, the default behavior is to show those nodes and emit a warning.
- Automatic node expansion is opt-in via `TEXT2CYPHER_ENABLE_NODE_EXPANSION=true`.
- Expansion is bounded by `TEXT2CYPHER_EXPANSION_PER_NODE_LIMIT` and does not affect the canonical GraphRAG EvidenceSet.
- The UI supports manual one-hop node expansion through `/api/graph/node/expand/`.
- Manual expansion is exploratory and user-triggered; the system should not silently deepen the graph view.
- `MeetingItem` expansion is scope-based instead of all-at-once:
  - `meeting`
  - `owner`
  - `dates`
  - `product_regulation`
  - `keyword`
  - `semantic`
- Expansion examples:
  - `Date` -> `MeetingItem-[:HAS_PLANNED_DATE|HAS_COMPLETED_DATE]->Date` plus parent `Meeting`.
  - `Person` -> `MeetingItem-[:RESPONSIBLE_BY]->Person` plus parent `Meeting`.
  - `Product` -> `MeetingItem-[:MENTIONS_PRODUCT]->Product` plus parent `Meeting`.
  - `Regulation` -> `MeetingItem-[:MENTIONS_REGULATION]->Regulation` plus parent `Meeting`.

Use it for exploratory questions such as:

- `哪些產品跨最多會議被討論？`
- `哪些人負責最多事項？`
- `哪些會議同時提到 FDA 和 TFDA？`
- `哪些 issue 沒有 follow-up？`
- `哪些產品和法規最常一起出現？`
