from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pymongo import MongoClient


BASE = Path.cwd()
OUT_DIR = BASE / "docs" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = OUT_DIR / "mongodb_logical_model.png"


COLLECTIONS = [
    {
        "name": "documents",
        "label": "文件",
        "keys": [
            ("document_id", "文件編號"),
            ("original_filename", "原始檔名"),
            ("stored_filename", "儲存檔名"),
            ("file_path", "檔案路徑"),
            ("file_ext", "副檔名"),
            ("file_size", "檔案大小"),
            ("mime_type", "檔案型態"),
            ("doc_type", "文件類型"),
            ("status", "處理狀態"),
            ("page_count", "頁數"),
            ("created_at / updated_at", "建立／更新時間"),
        ],
    },
    {
        "name": "meeting_minutes",
        "label": "會議主檔",
        "keys": [
            ("meeting_id", "會議編號"),
            ("document_id", "來源文件編號"),
            ("company_name", "公司名稱"),
            ("form_title / form_no", "表單標題／編號"),
            ("ref_no", "參考編號"),
            ("meeting_name", "會議名稱"),
            ("meeting_date", "會議日期"),
            ("start_time / end_time", "起迄時間"),
            ("location", "地點"),
            ("chairperson / recorder", "主席／記錄人"),
            ("responsible_unit", "權責單位"),
            ("attendees", "出席人員"),
            ("status", "處理狀態"),
        ],
    },
    {
        "name": "meeting_items",
        "label": "會議項目",
        "keys": [
            ("item_id", "會議項目編號"),
            ("meeting_id", "所屬會議編號"),
            ("document_id", "來源文件編號"),
            ("item_no", "項次"),
            ("content", "會議內容"),
            ("owner", "負責人"),
            ("planned_date", "預計完成日"),
            ("actual_completed_date", "實際完成日"),
            ("tracking_result", "追蹤結果"),
            ("page_number", "來源頁碼"),
            ("raw_row_text", "原始列文字"),
            ("source", "來源資訊"),
            ("status", "項目狀態"),
            ("status_source / confidence", "狀態來源／信心值"),
        ],
    },
]


def load_env() -> None:
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_counts() -> dict[str, int]:
    load_env()
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB_NAME", "document_retrieval_system")
    client = MongoClient(uri, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    db = client[db_name]
    return {item["name"]: db[item["name"]].count_documents({}) for item in COLLECTIONS}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc"),
        Path("C:/Windows/Fonts/mingliub.ttc" if bold else "C:/Windows/Fonts/mingliu.ttc"),
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def text_center(draw: ImageDraw.ImageDraw, xy, text: str, fnt, fill):
    x1, y1, x2, y2 = xy
    bbox = draw.textbbox((0, 0), text, font=fnt)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((x1 + (x2 - x1 - tw) / 2, y1 + (y2 - y1 - th) / 2), text, font=fnt, fill=fill)


def rounded_box(draw, xy, radius=22, fill="#ffffff", outline="#222222", width=3):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def arrow(draw, start, end, fill="#2c3e50", width=5):
    draw.line([start, end], fill=fill, width=width)
    x1, y1 = start
    x2, y2 = end
    # Right-pointing arrowhead.
    draw.polygon([(x2, y2), (x2 - 22, y2 - 12), (x2 - 22, y2 + 12)], fill=fill)


def dashed_arrow(draw, points, fill="#6b7280", width=4, dash=16):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length == 0:
            continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        pos = 0
        while pos < length:
            end = min(pos + dash, length)
            draw.line(
                [(x1 + dx * pos, y1 + dy * pos), (x1 + dx * end, y1 + dy * end)],
                fill=fill,
                width=width,
            )
            pos += dash * 1.8
    x, y = points[-1]
    draw.polygon([(x, y), (x - 18, y - 10), (x - 18, y + 10)], fill=fill)


def draw_collection(draw, x, y, w, h, collection, count):
    border = "#1f2937"
    header = "#edf2f7"
    accent = "#2563eb"
    rounded_box(draw, (x, y, x + w, y + h), fill="#ffffff", outline=border, width=3)
    draw.rounded_rectangle((x, y, x + w, y + 92), radius=22, fill=header, outline=border, width=3)
    draw.rectangle((x, y + 58, x + w, y + 92), fill=header)
    draw.line([(x, y + 92), (x + w, y + 92)], fill=border, width=3)

    title_font = font(30, bold=True)
    sub_font = font(20)
    field_font = font(19)
    muted = "#4b5563"

    text_center(draw, (x, y + 10, x + w, y + 50), f"{collection['name']} collection", title_font, "#111827")
    text_center(draw, (x, y + 50, x + w, y + 86), f"{collection['label']}｜{count} 筆", sub_font, accent)

    yy = y + 112
    for key, desc in collection["keys"]:
        key_fill = "#111827" if key in {"document_id", "meeting_id", "item_id"} else "#374151"
        draw.text((x + 28, yy), key, font=field_font, fill=key_fill)
        draw.text((x + 250, yy), f"（{desc}）", font=field_font, fill=muted)
        yy += 34


def main():
    counts = get_counts()
    img = Image.new("RGB", (2600, 1280), "#ffffff")
    draw = ImageDraw.Draw(img)

    title_font = font(42, bold=True)
    note_font = font(24)
    rel_font = font(24, bold=True)
    small_font = font(21)

    text_center(
        draw,
        (0, 28, 2600, 90),
        "MongoDB 結構化資料模型與來源回溯關係",
        title_font,
        "#111827",
    )
    text_center(
        draw,
        (0, 88, 2600, 132),
        "以 collection 與文件欄位呈現；連線為應用層邏輯參照，非關聯式資料庫外鍵約束",
        note_font,
        "#4b5563",
    )

    boxes = [
        (90, 190, 600, 780),
        (930, 190, 650, 780),
        (1870, 190, 640, 780),
    ]

    for box, collection in zip(boxes, COLLECTIONS):
        x, y, w, h = box
        draw_collection(draw, x, y, w, h, collection, counts.get(collection["name"], 0))

    # Main hierarchy arrows.
    arrow(draw, (690, 555), (930, 555), fill="#2563eb", width=6)
    draw.rounded_rectangle((720, 462, 900, 535), radius=14, fill="#ffffff", outline="#bfdbfe", width=2)
    text_center(draw, (720, 468, 900, 500), "包含多場會議", rel_font, "#1d4ed8")
    text_center(draw, (720, 500, 900, 530), "document_id", small_font, "#4b5563")

    arrow(draw, (1580, 555), (1870, 555), fill="#2563eb", width=6)
    draw.rounded_rectangle((1630, 462, 1818, 535), radius=14, fill="#ffffff", outline="#bfdbfe", width=2)
    text_center(draw, (1630, 468, 1818, 500), "包含多筆項目", rel_font, "#1d4ed8")
    text_center(draw, (1630, 500, 1818, 530), "meeting_id", small_font, "#4b5563")

    # Direct source trace from Document to MeetingItem via document_id.
    dashed_arrow(draw, [(690, 880), (1290, 1065), (1870, 880)], fill="#6b7280", width=4)
    text_center(draw, (760, 1028, 1830, 1088), "MeetingItem 亦保留 document_id，可直接回溯原始文件來源", small_font, "#374151")

    # Footer note.
    draw.rounded_rectangle((220, 1120, 2380, 1200), radius=18, fill="#f9fafb", outline="#d1d5db", width=2)
    note = "核心識別欄位：document_id 串接文件與會議；meeting_id 串接會議與會議項目；item_id 作為 GraphRAG、Neo4j 與 Qdrant 回查同一筆會議項目的共同鍵。"
    text_center(draw, (240, 1134, 2360, 1186), note, small_font, "#111827")

    img.save(OUT_PATH, dpi=(300, 300))
    print(OUT_PATH)


if __name__ == "__main__":
    main()
