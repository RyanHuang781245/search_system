from pathlib import Path

from docx import Document
from docx.shared import RGBColor


BASE = Path.cwd()
FINAL_SUFFIX = "_\u7b2c\u516d\u7ae0\u8207\u9644\u9304\u5b8c\u6210.docx"


def set_red(paragraph):
    for run in paragraph.runs:
        run.font.color.rgb = RGBColor(255, 0, 0)


def main():
    candidates = sorted(
        BASE.glob(f"*\u7b2c\u516d\u7ae0\u8207\u9644\u9304\u5b8c\u6210.docx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("No final DOCX found.")

    docx_path = candidates[0]
    doc = Document(docx_path)

    toc_updates = {
        "5.6 GraphRAG \u6aa2\u7d22\u56de\u61c9\u6210\u679c": "43",
        "5.7 \u8207\u5176\u4ed6\u6aa2\u7d22\u65b9\u6cd5\u4e4b\u6bd4\u8f03": "45",
        "5.8 Text2Cypher \u67e5\u8a62\u6210\u679c": "47",
        "5.9 \u7d9c\u5408\u8a0e\u8ad6\u8207\u7814\u7a76\u8ca2\u737b": "48",
        "5.10 \u932f\u8aa4\u985e\u578b\u8207\u9650\u5236\u5206\u6790": "49",
        "\u7b2c\u516d\u7ae0 \u7d50\u8ad6\u8207\u672a\u4f86\u767c\u5c55": "51",
        "6.1 \u7814\u7a76\u7d50\u8ad6": "51",
        "6.2 \u7814\u7a76\u9650\u5236": "52",
        "6.3 \u672a\u4f86\u767c\u5c55": "52",
        "\u53c3\u8003\u6587\u737b": "54",
        "\u9644\u9304A GraphRAG \u6e2c\u8a66\u554f\u984c\u8207\u5224\u5b9a\u7d50\u679c": "57",
    }

    changed = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        for title, page in toc_updates.items():
            if text.startswith(title) and "\t" in text:
                paragraph.text = f"{title}\t{page}"
                set_red(paragraph)
                changed.append((title, page))
                break

    missing = [title for title in toc_updates if title not in {c[0] for c in changed}]
    if missing:
        raise SystemExit(f"Missing TOC entries: {missing}")

    doc.save(docx_path)
    print(docx_path)
    for title, page in changed:
        print(f"{title}\\t{page}")


if __name__ == "__main__":
    main()
