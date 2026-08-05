# 圖 5.2 至圖 5.7 修訂建議稿

## 整體呈現方式建議

建議將圖 5.2 至圖 5.7 的呈現方式調整為「查詢問題 + 系統回答畫面 + ID 對照表 + 結果說明」。圖中的 meeting_id 與 item_id 可保留，用來呈現來源回溯能力；但圖下方需補充對照表，讓讀者知道每個 ID 對應的會議項目內容。圖片本身建議重新截圖或輸出高解析版本，保留問題、回答、來源證據與圖譜節點四個區塊即可，避免畫面過寬導致文字縮小。

圖片解析度建議採 300 dpi 以上，或以瀏覽器放大 125% 至 150% 後重新截圖。若頁面資訊過多，可將「回答區」與「來源證據/圖譜區」拆成兩張子圖，或在圖中以紅框標示查詢問題、回答、來源 ID 與高亮節點，讓讀者先看出重點，再由下方表格確認 ID 對應內容。

## 圖 5.2 責任歸屬型查詢

查詢問題：Person_F03E4ECA0A 負責哪些項目？

建議補充文字：

圖 5.2 顯示責任歸屬型問題的查詢結果。系統依據 MeetingItem 的 owner 欄位與知識圖譜中的 RESPONSIBLE_BY 關係，找出 Person_F03E4ECA0A 對應的 11 筆會議項目。此結果證明系統不是只依關鍵字比對人名，而是能回到結構化欄位中的負責人資訊，並將每一筆回答連結到具體的 meeting_id、item_id 與 item_no。

| evidence_id | meeting_id | item_id | item_no | 會議項目內容 |
|---|---|---|---|---|
| evidence_001 | meeting_6104c92cd679 | item_03cc4d4684a4 | 07 | 確認 HA coating 代工廠商的委外費用與 MOQ |
| evidence_002 | meeting_6104c92cd679 | item_0759f3eddbfe | 05 | 請 UR3 確認 cemented type 的 stem 可搭配的 centralizer 與 restrictor |
| evidence_003 | meeting_6104c92cd679 | item_080f7ac90d2c | 13 | 請 UR3 將 corail stem 寄給高雄鍛造工程師參考，並協助去除 HA，進行表面溝槽特徵 R 角量測 |
| evidence_004 | meeting_6104c92cd679 | item_44b7149bd5ed | 11 | Cementless 系列可先開發，Cemented 後續再開發，請 UR3 再評估開發時程 |
| evidence_005 | meeting_a56ecf6f5aa6 | item_33844f67cc0c | 02 | 與 UR4 法規確認 TFDA 工單樣品數量為 10 支 |
| evidence_006 | meeting_a56ecf6f5aa6 | item_622856e0d06d | 09 | 提供標籤狀況給 UR4 確認，詳如附件 |
| evidence_007 | meeting_a56ecf6f5aa6 | item_b022f6c14ea5 | 05 | 確認所有輸出文件的時間 |
| evidence_008 | meeting_a56ecf6f5aa6 | item_b71498f44942 | 01 | 評估 cemented stem 的開發與送件時間 |
| evidence_009 | meeting_a56ecf6f5aa6 | item_d1469cd2e0d9 | 10 | 包裝部分待競品購入後再進行確認 |
| evidence_010 | meeting_a56ecf6f5aa6 | item_d2d008c26cdd | 06 | 修正產品名稱，除 Conformity 大寫外，其餘小寫 |
| evidence_011 | meeting_7958791265f8 | item_949241ecafd5 | 08 | 法規開時間與導量產時間需於後續確認是否需進行 impingement 測試後提供 |

## 圖 5.3 時程狀態型查詢

查詢問題：2017 年 12 月 15 日要完成哪些事項？

建議補充文字：

圖 5.3 顯示時程狀態型問題的查詢結果。系統以預計完成日期 2017-12-15 作為查詢條件，透過 planned_date 欄位與 HAS_PLANNED_DATE 關係找出 5 筆待完成事項。此結果證明系統能依日期欄位定位任務，而不是僅搜尋內文是否出現日期字串。

| evidence_id | meeting_id | item_id | item_no | 預計日期 | 會議項目內容 |
|---|---|---|---|---|---|
| evidence_001 | meeting_6104c92cd679 | item_78a76358cd2d | 06 | 2017-12-15 | 請 UPD 與法國分公司確認歐洲地區需求與數量預估 |
| evidence_002 | meeting_6104c92cd679 | item_0759f3eddbfe | 05 | 2017-12-15 | 請 UR3 確認 cemented type 的 stem 可搭配的 centralizer 與 restrictor |
| evidence_003 | meeting_6104c92cd679 | item_dff12fe5b092 | 04 | 2017-12-15 | 請 UPD 與大陸的 Elisa 確認 corail stem 在大陸地區是否有需求及訂單預估量 |
| evidence_004 | meeting_6104c92cd679 | item_ccb4ee8281e5 | 03 | 2017-12-15 | 請 UPD 確認系統名與產品名稱，是否使用代號或縮寫 |
| evidence_005 | meeting_6104c92cd679 | item_3d250d7d78e1 | 02 | 2017-12-15 | 請 UPD 確認 cemented type 的 Stem 品號及是否需增加品號 |

## 圖 5.4 法規關聯型查詢

查詢問題：FDA 相關會議項目有哪些？

建議補充文字：

圖 5.4 顯示法規關聯型問題的查詢結果。系統利用 Regulation 節點與 MENTIONS_REGULATION 關係找出與 FDA 送件或認證脈絡相關的會議項目。結果中部分項目同時提及 CE、TFDA、CFDA 等法規，因此圖譜可呈現法規共現脈絡；正文表格則應以唯一 item_id 列出，避免讀者誤以為同一會議項目被重複計算。

| evidence_id | meeting_id | item_id | item_no | 命中法規/脈絡 | 會議項目內容 |
|---|---|---|---|---|---|
| evidence_001-003 | meeting_a56ecf6f5aa6 | item_2ae9866a4ae2 | 03 | CE / FDA / TFDA / CFDA | 產品預計申請地區為 CE、FDA、TFDA、CFDA，並請人員協助確認是否有日本送件需求 |
| evidence_004 | meeting_a56ecf6f5aa6 | item_33844f67cc0c | 02 | TFDA 法規送件脈絡 | 與 UR4 法規確認 TFDA 工單樣品數量為 10 支 |
| evidence_005-007 | meeting_7958791265f8 | item_c15b532d79ee | 05 | CE / FDA / TFDA / CFDA / PMDA | 註冊預計申請地區為 CE、FDA、TFDA、CFDA、PMDA，CE 認證與 cementless type 一起送 |
| evidence_008 | meeting_5f8810d5b2f5 | item_cfede8f15778 | 01 | FDA | 工程圖發出延後 1 個月，10/31 完成；認證以 FDA 優先，人力需重新安排 |

## 圖 5.5 關鍵詞探索型查詢

查詢問題：stem 相關的會議項目有哪些？

建議補充文字：

圖 5.5 顯示關鍵詞探索型問題的查詢結果。系統以 stem 相關產品詞為線索，透過 MENTIONS_PRODUCT 與會議項目展開找出 20 個唯一來源項目。此結果證明 GraphRAG 可從單一關鍵詞延伸到不同會議中的產品名稱、測試項目、法規送件與器械設計討論，支援探索式查詢。

| evidence_id | meeting_id | item_id | item_no | 會議項目內容 |
|---|---|---|---|---|
| evidence_001 | meeting_523b2503e014 | item_04c4805d98fe | 03 | 請確定與 Stem 結合時，接觸點位置 |
| evidence_002 | meeting_523b2503e014 | item_b316794d86d3 | 06 | Lateral side 不需按比例漸進增加，寬度可參考 U2 Stem |
| evidence_003 | meeting_523b2503e014 | item_c91bd04ed89c | 07 | 將 U2 stem 剖切確定其 taper 角度 |
| evidence_004 | meeting_523b2503e014 | item_dc68cc37d715 | 03 | 請比較各廠牌及 UTF Stem 各尺寸使用量以決定 increment |
| evidence_005 | meeting_523b2503e014 | item_f65afa4731e5 | 02 | Short stem 的 stem length 訂為 90-130 mm |
| evidence_006-007 | meeting_002152b53a27 | item_147c96db8598 | 01 | 系統名稱與產品名稱包含 United Hip System 與 Locking cage 等項目 |
| evidence_008 | meeting_6104c92cd679 | item_080f7ac90d2c | 13 | 請 UR3 將 corail stem 寄給高雄鍛造工程師參考並協助量測表面溝槽特徵 R 角 |
| evidence_009 | meeting_6104c92cd679 | item_dff12fe5b092 | 04 | 請 UPD 與大陸的 Elisa 確認 corail stem 在大陸地區是否有需求 |
| evidence_010 | meeting_a56ecf6f5aa6 | item_94ae44eebcfe | 04 | 實質對等產品為 Depuy 的 Corail stem |
| evidence_011 | meeting_a56ecf6f5aa6 | item_b71498f44942 | 01 | 評估 cemented stem 的開發與送件時間 |
| evidence_012-014 | meeting_7958791265f8 | item_288727fdb3c3 | 04 | 系統名 United Hip System；產品名包含 Conformity stem, short neck, collared, #1 |
| evidence_015 | meeting_7958791265f8 | item_4ff7e4cd633c | 09 | Stem 預計可與 Metal head 以及 ceramic head 搭配 |
| evidence_016 | meeting_7958791265f8 | item_6f46546181ac | 06 | 建議統一 conformity stem 系列中英文品名 |
| evidence_017 | meeting_7958791265f8 | item_fd59ad491db4 | 03 | 實質對等產品為 Corail stem 與 MetaFix |
| evidence_018-019 | meeting_5f8810d5b2f5 | item_44e4661e47a2 | 03 | 預計 Modular system 器械包含 Canal finder rasp、Stem inserter 等項目 |
| evidence_020 | meeting_523b2503e014 | item_e04c6d7a1cd4 | 01 | 執行 Pull-out test 確定角度標稱值修改是否影響結合強度 |
| evidence_021 | meeting_523b2503e014 | item_4437863f2db3 | 02 | Taper length 確定為 10 mm |
| evidence_022 | meeting_523b2503e014 | item_d1441ca67cf8 | 03 | 36 mm 球頭之切角起始位置需為球頭高度的 3/4 |
| evidence_023 | meeting_523b2503e014 | item_166880fead27 | 04 | 請提出新球頭在不同切角狀況時之外觀以協助最終產品外觀決定 |
| evidence_024 | meeting_523b2503e014 | item_a8bba5dc451b | 05 | 請訂出相關測試及送件時程 |

## 圖 5.6 開放模糊型查詢

查詢問題：P1812 Coformity stem 會議進度與會議摘要

建議補充文字：

圖 5.6 顯示開放模糊型問題的查詢結果。使用者並未指定單一欄位，而是要求會議進度與摘要；系統先定位 P1812 Coformity stem 器械進度會議，再彙整該會議的 4 筆 MeetingItem。此結果證明系統能將開放式問題轉換為會議項目層級的摘要，且摘要內容仍可回溯至具體來源。

| evidence_id | meeting_id | item_id | item_no | 會議項目內容 |
|---|---|---|---|---|
| evidence_001 | meeting_5f8810d5b2f5 | item_cfede8f15778 | 01 | 工程圖發出延後 1 個月，10/31 完成；認證以 FDA 優先，人力需重新安排 |
| evidence_002 | meeting_5f8810d5b2f5 | item_069594007412 | 02 | Modular handle 具備正敲、反敲與抗旋轉功能，初步設定金屬加塑膠方式 |
| evidence_003 | meeting_5f8810d5b2f5 | item_44e4661e47a2 | 03 | 預計 Modular system 器械包含 Canal finder rasp、Stem inserter、Femoral head remover 等項目 |
| evidence_004 | meeting_5f8810d5b2f5 | item_a14301e0155c | 04 | 維持 Male broach Type |

## 圖 5.7 資料不足型查詢

建議補充文字：

圖 5.7 顯示資料不足型問題的拒答結果。當查詢實體不存在或找不到符合條件的來源項目時，系統不產生無根據回答，而是回覆資料不足。此結果證明 GraphRAG 回答受到來源證據限制，可降低模型臆測風險。

| 查詢問題 | 找到來源數 | 系統行為 | 說明 |
|---|---:|---|---|
| Person_DEADBEEF00 負責哪些項目？ | 0 | 拒答 | 無符合 owner 欄位或 RESPONSIBLE_BY 關係的來源 |
| 2099 年 01 月 01 日要完成哪些事項？ | 0 | 拒答 | 無符合 planned_date 或 HAS_PLANNED_DATE 關係的來源 |
| Regulation_FAKE000000 相關會議項目有哪些？ | 0 | 拒答 | 無符合法規節點或 MENTIONS_REGULATION 關係的來源 |

