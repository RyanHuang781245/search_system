import re
from datetime import date
from uuid import uuid4

from apps.item_status import is_meaningful_value


FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９．／－", "0123456789./-")
ITEM_NO_PATTERN = re.compile(r"^[0-9０-９]{1,2}[.]?$")


def parse_meeting_minutes(pdf_payload, document_id):
    raw_text = pdf_payload["raw_text"]
    if _needs_ocr(pdf_payload, raw_text):
        return {
            "status": "needs_ocr",
            "meeting_minutes": None,
            "meeting_items": [],
            "raw_text": raw_text,
            "page_count": pdf_payload["page_count"],
        }

    metadata = _extract_metadata(raw_text, pdf_payload["page_count"])
    meeting_id = f"meeting_{uuid4().hex[:12]}"
    items = _extract_items(pdf_payload["pages"], metadata["meeting_date"], meeting_id, document_id)

    meeting_minutes = {
        "meeting_id": meeting_id,
        "document_id": document_id,
        "company_name": metadata["company_name"],
        "form_title": metadata["form_title"],
        "form_no": metadata["form_no"],
        "ref_no": metadata["ref_no"],
        "meeting_name": metadata["meeting_name"],
        "meeting_date": metadata["meeting_date"],
        "start_time": metadata["start_time"],
        "end_time": metadata["end_time"],
        "location": metadata["location"],
        "chairperson": metadata["chairperson"],
        "recorder": metadata["recorder"],
        "responsible_unit": metadata["responsible_unit"],
        "attendees": metadata["attendees"],
        "page_count": metadata["page_count"],
        "raw_text": raw_text,
        "status": "parsed",
    }

    return {
        "status": "parsed",
        "meeting_minutes": meeting_minutes,
        "meeting_items": items,
        "raw_text": raw_text,
        "page_count": pdf_payload["page_count"],
    }


def _needs_ocr(pdf_payload, raw_text):
    normalized = _normalize_text(raw_text)
    return (
        pdf_payload["word_count"] < 40
        or len(normalized) < 80
        or "會議記錄單" not in normalized
    )


def _extract_metadata(raw_text, page_count):
    normalized = _normalize_text(raw_text)
    readable_text = _normalize_readable_text(raw_text)
    company_name = _search_value(readable_text, r"(聯合骨科器材股份有限公司)", default=None)
    form_title = "會議記錄單" if "會議記錄單" in normalized else None
    form_no = _search_value(readable_text, r"(Q-[A-Z0-9\/-]+)")
    ref_no = _search_value(readable_text, r"Ref\s*:\s*([A-Z0-9-]+)")

    year, month, day_num = _search_groups(
        readable_text,
        r"時\s*間\s*:\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    )
    meeting_date = None
    if year and month and day_num:
        meeting_date = f"{int(year):04d}-{int(month):02d}-{int(day_num):02d}"

    start_hour, start_minute, end_hour, end_minute = _search_groups(
        readable_text,
        r"(\d{1,2})\s*時\s*(\d{1,2})\s*分\s*~\s*(\d{1,2})\s*時\s*(\d{1,2})\s*分",
    )
    start_time = _format_time(start_hour, start_minute)
    end_time = _format_time(end_hour, end_minute)

    location = _search_value(readable_text, r"地\s*點\s*:\s*(.+?)\s*主\s*席\s*:")
    chairperson = _search_value(readable_text, r"主\s*席\s*:\s*(.+?)\s*記\s*錄\s*:")
    recorder = _search_value(readable_text, r"記\s*錄\s*:\s*(.+?)\s*會\s*議\s*名\s*稱\s*:")
    meeting_name = _search_value(
        readable_text,
        r"會\s*議\s*名\s*稱\s*:\s*(.+?)\s*權\s*責\s*單\s*位\s*:",
    )
    responsible_unit = _search_value(
        readable_text,
        r"權\s*責\s*單\s*位\s*:\s*(.+?)\s*出\s*席\s*人\s*員\s*:",
    )
    attendees_text = _search_value(
        readable_text,
        r"出\s*席\s*人\s*員\s*:\s*(.+?)\s*項\s*次",
        default="",
        clean=False,
    )
    attendees = _split_attendees(attendees_text)

    return {
        "company_name": company_name,
        "form_title": form_title,
        "form_no": form_no,
        "ref_no": ref_no,
        "meeting_name": meeting_name,
        "meeting_date": meeting_date,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "chairperson": chairperson,
        "recorder": recorder,
        "responsible_unit": responsible_unit,
        "attendees": attendees,
        "page_count": page_count,
    }


def _extract_items(pages, meeting_date, meeting_id, document_id):
    table_items = _extract_items_from_tables(pages, meeting_date, meeting_id, document_id)
    if table_items:
        return table_items

    return _extract_items_from_words(pages, meeting_date, meeting_id, document_id)


def _extract_items_from_tables(pages, meeting_date, meeting_id, document_id):
    items = []
    for page in pages:
        for table in page.get("tables", []):
            for row in table.get("rows", []):
                if not row or not row[0]:
                    continue
                item_no = _normalize_item_no(row[0])
                if not item_no:
                    continue
                content = _clean_multiline_text(row[1] if len(row) > 1 else None)
                owner = _normalize_nullable(row[2] if len(row) > 2 else None)
                planned_date = _normalize_partial_date(row[3] if len(row) > 3 else None, meeting_date)
                actual_completed_date = _normalize_partial_date(row[4] if len(row) > 4 else None, meeting_date)
                tracking_result = _normalize_nullable(row[5] if len(row) > 5 else None)
                raw_row_text = _clean_multiline_text(" ".join(str(cell or "") for cell in row))
                if not any([content, owner, planned_date, actual_completed_date, tracking_result]):
                    continue
                items.append(
                    {
                        "item_id": f"item_{uuid4().hex[:12]}",
                        "meeting_id": meeting_id,
                        "document_id": document_id,
                        "item_no": item_no,
                        "content": content,
                        "owner": owner,
                        "planned_date": planned_date,
                        "actual_completed_date": actual_completed_date,
                        "tracking_result": tracking_result,
                        "page_number": page["page_number"],
                        "raw_row_text": raw_row_text,
                        "source": "pymupdf",
                    }
                )
    return items


def _extract_items_from_words(pages, meeting_date, meeting_id, document_id):
    items = []
    expected_item_no = None

    for page in pages:
        words = [word for word in page["words"] if word[4].strip()]
        header_bottom = _find_table_header_bottom(words)
        if header_bottom is None:
            continue

        anchors = _find_item_anchors(words, header_bottom, expected_item_no)
        if not anchors:
            continue

        page_items = _extract_page_rows(
            words=words,
            anchors=anchors,
            header_bottom=header_bottom,
            page_height=page["height"],
            meeting_date=meeting_date,
            meeting_id=meeting_id,
            document_id=document_id,
            page_number=page["page_number"],
        )
        if page_items:
            items.extend(page_items)
            expected_item_no = int(page_items[-1]["item_no"]) + 1

    return items


def _find_table_header_bottom(words):
    header_words = []
    for word in words:
        text = _normalize_text(word[4])
        if text in {"項次", "負責人", "預計", "日期", "實際", "完成日", "追蹤", "結果"}:
            header_words.append(word)
    if not header_words:
        return None
    return max(word[3] for word in header_words) + 6


def _find_item_anchors(words, header_bottom, expected_item_no):
    candidates = []
    for word in words:
        text = word[4].strip()
        if word[0] > 85 or word[1] <= header_bottom or not ITEM_NO_PATTERN.match(text):
            continue
        candidates.append({"text": text, "y0": word[1], "y1": word[3], "x0": word[0]})

    candidates.sort(key=lambda item: item["y0"])
    anchors = []
    next_expected = expected_item_no

    for candidate in candidates:
        normalized_no = _normalize_item_no(candidate["text"])
        if normalized_no is None:
            continue
        numeric_no = int(normalized_no)
        if next_expected is not None and numeric_no != next_expected:
            continue
        if anchors and candidate["y0"] - anchors[-1]["y0"] < 22:
            continue
        candidate["item_no"] = normalized_no
        anchors.append(candidate)
        next_expected = numeric_no + 1

    if anchors or expected_item_no is not None:
        return anchors

    filtered = []
    last_numeric_no = None
    for candidate in candidates:
        normalized_no = _normalize_item_no(candidate["text"])
        if normalized_no is None:
            continue
        numeric_no = int(normalized_no)
        if last_numeric_no is not None and numeric_no <= last_numeric_no:
            continue
        if filtered and candidate["y0"] - filtered[-1]["y0"] < 22:
            continue
        candidate["item_no"] = normalized_no
        filtered.append(candidate)
        last_numeric_no = numeric_no
    return filtered


def _extract_page_rows(
    words,
    anchors,
    header_bottom,
    page_height,
    meeting_date,
    meeting_id,
    document_id,
    page_number,
):
    rows = []
    boundaries = [header_bottom]
    boundaries.extend((anchors[index]["y0"] + anchors[index + 1]["y0"]) / 2 for index in range(len(anchors) - 1))
    boundaries.append(page_height - 12)

    for index, anchor in enumerate(anchors):
        row_words = [
            word
            for word in words
            if boundaries[index] <= word[1] < boundaries[index + 1]
        ]
        if not row_words:
            continue

        row = _build_meeting_item(
            row_words=row_words,
            item_no=anchor["item_no"],
            meeting_date=meeting_date,
            meeting_id=meeting_id,
            document_id=document_id,
            page_number=page_number,
        )
        if row:
            rows.append(row)
    return rows


def _build_meeting_item(row_words, item_no, meeting_date, meeting_id, document_id, page_number):
    column_words = {
        "content": [],
        "owner": [],
        "planned_date": [],
        "actual_completed_date": [],
        "tracking_result": [],
    }

    for word in row_words:
        x0 = word[0]
        if x0 < 80:
            continue
        if x0 < 375:
            column_words["content"].append(word)
        elif x0 < 430:
            column_words["owner"].append(word)
        elif x0 < 475:
            column_words["planned_date"].append(word)
        elif x0 < 525:
            column_words["actual_completed_date"].append(word)
        else:
            column_words["tracking_result"].append(word)

    content = _join_words(column_words["content"])
    owner = _normalize_nullable(_join_words(column_words["owner"]))
    planned_date = _normalize_partial_date(_join_words(column_words["planned_date"]), meeting_date)
    actual_completed_date = _normalize_partial_date(
        _join_words(column_words["actual_completed_date"]),
        meeting_date,
    )
    tracking_result = _normalize_nullable(_join_words(column_words["tracking_result"]))

    raw_row_text = _join_words(sorted(row_words, key=lambda word: (round(word[1], 1), word[0])))
    if not any([content, owner, planned_date, actual_completed_date, tracking_result]):
        return None

    return {
        "item_id": f"item_{uuid4().hex[:12]}",
        "meeting_id": meeting_id,
        "document_id": document_id,
        "item_no": item_no,
        "content": content,
        "owner": owner,
        "planned_date": planned_date,
        "actual_completed_date": actual_completed_date,
        "tracking_result": tracking_result,
        "page_number": page_number,
        "raw_row_text": raw_row_text,
        "source": "pymupdf",
    }


def _join_words(words):
    if not words:
        return ""

    sorted_words = sorted(words, key=lambda word: (round(word[1], 1), word[0]))
    lines = []
    current_line = []
    current_y = None

    for word in sorted_words:
        y0 = round(word[1], 1)
        text = word[4].strip()
        if current_y is None or abs(y0 - current_y) <= 3:
            current_line.append(word)
            current_y = y0 if current_y is None else current_y
            continue
        lines.append(" ".join(part[4].strip() for part in sorted(current_line, key=lambda item: item[0])))
        current_line = [word]
        current_y = y0

    if current_line:
        lines.append(" ".join(part[4].strip() for part in sorted(current_line, key=lambda item: item[0])))

    return _clean_text(" ".join(line.strip() for line in lines if line.strip()))


def _normalize_text(value):
    return re.sub(r"\s+", "", str(value or "")).translate(FULLWIDTH_DIGITS)


def _clean_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = _repair_cjk_spacing(text)
    return text or None


def _clean_multiline_text(value):
    text = str(value or "").replace("\n", " ")
    return _clean_text(text)


def _normalize_readable_text(value):
    text = str(value or "").translate(FULLWIDTH_DIGITS)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text


def _search_value(text, pattern, default=None, clean=True):
    match = re.search(pattern, text, re.S)
    if not match:
        return default
    value = match.group(1)
    if not clean:
        return str(value or "").strip()
    return _clean_text(value)


def _search_groups(text, pattern):
    match = re.search(pattern, text, re.S)
    if not match:
        return (None, None, None)
    return match.groups()


def _format_time(hour, minute):
    if hour is None or minute is None:
        return None
    return f"{int(hour):02d}:{int(minute):02d}"


def _split_attendees(attendees_text):
    raw_text = str(attendees_text or "").strip()
    if not raw_text:
        return []

    normalized = raw_text.replace("\n", " ")
    normalized = normalized.replace("、", ",").replace("，", ",")

    attendees = []
    seen = set()
    for segment in normalized.split(","):
        for name in _split_attendee_segment(segment):
            if name and name not in seen:
                seen.add(name)
                attendees.append(name)
    return attendees


def _split_attendee_segment(segment):
    cleaned = re.sub(r"\s+", " ", str(segment or "")).strip()
    if not cleaned:
        return []

    parts = cleaned.split(" ")
    if len(parts) == 2 and all(_is_cjk_token(part) for part in parts):
        if len(parts[0]) >= 2 and len(parts[1]) >= 2:
            return [_clean_attendee_name(part) for part in parts]
        return [_clean_attendee_name("".join(parts))]

    return [_clean_attendee_name(cleaned)]


def _clean_attendee_name(name):
    return _repair_cjk_spacing(re.sub(r"\s+", " ", str(name or "")).strip())


def _repair_cjk_spacing(text):
    return re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text)


def _is_cjk_token(value):
    return re.fullmatch(r"[\u3400-\u9fff]+", str(value or "")) is not None


def _normalize_item_no(value):
    text = str(value or "").strip().translate(FULLWIDTH_DIGITS)
    text = text.rstrip(".")
    if not text.isdigit():
        return None
    return f"{int(text):02d}"


def _normalize_partial_date(value, meeting_date):
    cleaned = _clean_text(value)
    if not is_meaningful_value(cleaned):
        return None

    normalized = cleaned.translate(FULLWIDTH_DIGITS)
    full_match = re.search(r"(\d{4})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{1,2})", normalized)
    if full_match:
        return _iso_date(*full_match.groups())

    zh_match = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", normalized)
    if zh_match:
        return _iso_date(*zh_match.groups())

    partial_match = re.search(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})", normalized)
    if partial_match and meeting_date:
        meeting_year = date.fromisoformat(meeting_date).year
        month, day_num = partial_match.groups()
        return _iso_date(meeting_year, month, day_num)

    return cleaned


def _iso_date(year, month, day_num):
    return f"{int(year):04d}-{int(month):02d}-{int(day_num):02d}"


def _normalize_nullable(value):
    cleaned = _clean_text(value)
    if not is_meaningful_value(cleaned):
        return None
    return cleaned
