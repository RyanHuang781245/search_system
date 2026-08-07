# 論文搜尋系統後端

這是論文系統的 Django 後端，負責文件上傳、會議紀錄解析、關鍵字搜尋、向量搜尋、圖譜搜尋與 GraphRAG 檢索問答。

## 專案目錄

- `apps/`：Django apps，包含文件、會議、圖譜、搜尋、向量、GraphRAG、隱私與解析功能。
- `config/`：Django 設定與 URL 路由。
- `templates/`：Console UI 使用的 HTML 頁面。
- `static/`：JavaScript 與 CSS 靜態資源。
- `docs/`：交接筆記與系統文件。
- `_handoff/`：封存的論文、簡報、實驗資料、範例資料、參考程式與一次性研究檔案。
- `uploads/`：執行期間的上傳檔案。Django 啟動時會重建此目錄，檔案已設定忽略。
- `work/`：本機匯出或暫存輸出目錄，已設定忽略。

## 環境建立

```powershell
uv sync
```

接著編輯 `.env`，設定 MongoDB、Neo4j、Qdrant 與 Ollama 的連線資訊。

## 執行系統

```powershell
python manage.py runserver
```

開啟 `http://127.0.0.1:8000/`。

主要頁面：

- `/documents/`
- `/meetings/`
- `/search/`
- `/graphrag/`
