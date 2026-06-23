| 對應表 3.5 類型 | 測試問題 | 主要檢索來源 | 評估重點 |
|:---:|:---:|:---:|:---:|
| 責任歸屬型 | Person_704118B2B1 負責哪些會議項目？ | 結構化欄位／圖譜關聯 | owner、RESPONSIBLE_BY |
| 責任歸屬型 | Person_35513ECC32 負責哪些事項？ | 結構化欄位／圖譜關聯 | 是否完整列出該負責人的 MeetingItem |
| 責任歸屬型 | Person_BDFC2032C6 負責哪些測試或時程相關項目？ | 結構化欄位／圖譜關聯 | 負責人與內容條件是否同時成立  |
| 時程狀態型 | 2017 年 12 月 15 日要完成哪些事項？ | 結構化欄位 | planned_date、HAS_PLANNED_DATE |
| 時程狀態型 | 2018 年 11 月 12 日實際完成哪些事項？ | 結構化欄位 | actual_completed_date、HAS_COMPLETED_DATE |
| 時程狀態型 | 已完成的事項有哪些？ | 結構化欄位 | tracking_result、actual_completed_date |
| 時程狀態型 | 不適用的事項有哪些？ | 結構化欄位 | tracking_result 是否正確判斷 |
| 關鍵詞探索型 | Fatigue test 相關會議項目有哪些？ | 圖譜關聯／語意檢索 | MENTIONS、Keyword、semantic |
| 關鍵詞探索型 | 風險管理報告相關確認事項有哪些？ | 圖譜關聯／語意檢索 | 關鍵詞命中與來源回溯 |
| 關鍵詞探索型 | 測試報告確認相關項目有哪些？ | 圖譜關聯／語意檢索 | 是否召回相關 MeetingItem |
| 產品或法規關聯型 | Locking cage 被哪些會議項目提及？ | 圖譜關聯 | MENTIONS_PRODUCT |
| 產品或法規關聯型 | Corail stem 相關事項有哪些？ | 圖譜關聯／結構化欄位 | Product 關聯與內容證據 |
| 產品或法規關聯型 | FDA 相關追蹤事項有哪些？ | 圖譜關聯／語意檢索 | MENTIONS_REGULATION、TRACKS_ISSUE |
| 產品或法規關聯型 | CE 相關會議項目有哪些？ | 圖譜關聯 | MENTIONS_REGULATION |
| 開放模糊型 | 有哪些決議需要整理？ | 語意檢索／圖譜關聯 | HAS_DECISION、摘要是否有來源 |
| 開放模糊型 | 有哪些風險或需注意事項？ | 語意檢索／圖譜關聯 | HAS_RISK、回答是否避免過度推論 |
| 開放模糊型 | 請整理 Conformity stem 的後續追蹤狀況。 | 語意檢索／圖譜關聯 | TRACKS_ISSUE、跨會議追蹤 |
| 資料不足型 | 不存在的人名負責哪些項目？	證據集合檢查 | 是否正確拒答 |
| 資料不足型 | 未出現在會議記錄中的決議是否已完成？ | 證據集合檢查 | 是否避免無來源生成 |