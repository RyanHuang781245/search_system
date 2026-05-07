from pathlib import Path

import fitz


class PDFTextExtractor:
    def __init__(self, file_path):
        self.file_path = Path(file_path)

    def extract(self):
        document = fitz.open(self.file_path)
        try:
            pages = []
            full_text_parts = []
            total_words = 0

            for index, page in enumerate(document):
                text = page.get_text("text")
                words = page.get_text("words")
                tables = []
                for table in page.find_tables().tables:
                    tables.append(
                        {
                            "bbox": list(table.bbox),
                            "rows": table.extract(),
                        }
                    )
                pages.append(
                    {
                        "page_number": index + 1,
                        "text": text,
                        "words": words,
                        "tables": tables,
                        "width": page.rect.width,
                        "height": page.rect.height,
                    }
                )
                full_text_parts.append(text)
                total_words += len(words)

            return {
                "page_count": document.page_count,
                "pages": pages,
                "raw_text": "\n".join(full_text_parts).strip(),
                "word_count": total_words,
            }
        finally:
            document.close()
