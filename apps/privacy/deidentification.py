from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings


MISSING_VALUES = {"", "-", "--", "na", "n/a", "none", "null"}
PERSON_FIELDS = {"chairperson", "recorder", "owner", "person", "person_name"}
UNIT_FIELDS = {"responsible_unit", "unit", "unit_name"}
COMPANY_FIELDS = {"company_name"}
LOCATION_FIELDS = {"location"}
FILE_FIELDS = {"original_filename"}
REF_FIELDS = {"form_no", "ref_no"}
TEXT_FIELDS = {
    "meeting_name",
    "content",
    "tracking_result",
    "raw_row_text",
    "raw_text",
    "description",
}
PASSTHROUGH_FIELDS = {
    "_id",
    "document_id",
    "meeting_id",
    "item_id",
    "stored_filename",
    "file_path",
    "absolute_file_path",
    "file_ext",
    "mime_type",
    "doc_type",
    "status",
    "status_source",
    "status_confidence",
    "meeting_date",
    "start_time",
    "end_time",
    "planned_date",
    "actual_completed_date",
    "created_at",
    "updated_at",
    "deleted_at",
    "file_modified_at",
    "page_count",
    "page_number",
    "file_size",
    "is_deleted",
    "source",
    "item_no",
}

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
TAIWAN_ID_PATTERN = re.compile(r"\b[A-Z][12]\d{8}\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def deidentification_enabled() -> bool:
    return bool(getattr(settings, "DEIDENTIFICATION_ENABLED", False))


def deidentify_document_record(document: dict) -> dict:
    if not deidentification_enabled():
        return document
    mapper = Deidentifier.from_values(collect_sensitive_values(document))
    return deidentify_value(document, mapper)


def deidentify_parsed_meeting_payload(parsed: dict) -> dict:
    if not deidentification_enabled() or parsed.get("status") != "parsed":
        return parsed

    source_values = {}
    meeting = parsed.get("meeting_minutes") or {}
    items = parsed.get("meeting_items") or []
    collect_sensitive_values(meeting, source_values)
    for item in items:
        collect_sensitive_values(item, source_values)

    mapper = Deidentifier.from_values(source_values)
    clean_payload = dict(parsed)
    clean_payload["meeting_minutes"] = deidentify_value(meeting, mapper)
    clean_payload["meeting_items"] = [deidentify_value(item, mapper) for item in items]
    clean_payload["raw_text"] = mapper.text(parsed.get("raw_text"))
    return clean_payload


class Deidentifier:
    def __init__(self, salt: str, values: dict[str, set[str]]):
        if not salt:
            raise ValueError("DEIDENTIFICATION_SALT is required when DEIDENTIFICATION_ENABLED=True.")
        self.salt = salt
        self.values = values
        self.mapping = {}
        self.replacements = []
        for kind, originals in values.items():
            for original in originals:
                replacement = self.pseudonym(kind, original)
                self.replacements.append((original, kind, replacement))
        self.replacements.sort(key=lambda item: len(item[0]), reverse=True)

    @classmethod
    def from_values(cls, values: dict[str, set[str]]) -> "Deidentifier":
        return cls(str(getattr(settings, "DEIDENTIFICATION_SALT", "") or "").strip(), values)

    def pseudonym(self, kind: str, value):
        text = normalize_value(value)
        if not text:
            return value
        prefixes = {
            "person": "Person",
            "unit": "Unit",
            "company": "Company",
            "location": "Location",
            "file": "File",
            "ref": "Ref",
        }
        digest = hashlib.sha256(f"{self.salt}\0{kind}\0{text}".encode("utf-8")).hexdigest()[:10].upper()
        replacement = f"{prefixes.get(kind, 'Token')}_{digest}"
        self.remember(kind, text, replacement)
        return replacement

    def filename(self, value):
        text = normalize_value(value)
        if not text:
            return value
        suffix = Path(text).suffix
        replacement = f"{self.pseudonym('file', text)}{suffix}"
        self.remember("file", text, replacement)
        return replacement

    def text(self, value):
        if not isinstance(value, str):
            return value
        result = value
        for original, kind, _replacement in self.replacements:
            result = result.replace(original, neutral_placeholder(kind))
        result = replace_pattern_tokens(result, self, EMAIL_PATTERN, "email", "Email")
        result = replace_pattern_tokens(result, self, TAIWAN_ID_PATTERN, "id", "ID")
        result = replace_pattern_tokens(result, self, PHONE_PATTERN, "phone", "Phone")
        return result

    def token(self, kind: str, value, prefix: str):
        text = normalize_value(value)
        if not text:
            return value
        digest = hashlib.sha256(f"{self.salt}\0{kind}\0{text}".encode("utf-8")).hexdigest()[:10].upper()
        replacement = f"{prefix}_{digest}"
        self.remember(kind, text, replacement)
        return replacement

    def remember(self, kind: str, original: str, anonymized: str) -> None:
        if original and anonymized and original != anonymized:
            self.mapping[(kind, original)] = anonymized
            write_mapping_records([{"kind": kind, "original": original, "anonymized": anonymized}])


def deidentify_value(value, mapper: Deidentifier, key: str = ""):
    if isinstance(value, dict):
        return {child_key: deidentify_value(child_value, mapper, child_key) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [deidentify_value(item, mapper, key) for item in value]
    if key in PASSTHROUGH_FIELDS:
        return value
    if key in PERSON_FIELDS or key == "attendees":
        return mapper.pseudonym("person", value)
    if key in UNIT_FIELDS:
        return mapper.pseudonym("unit", value)
    if key in COMPANY_FIELDS:
        return mapper.pseudonym("company", value)
    if key in LOCATION_FIELDS:
        return mapper.pseudonym("location", value)
    if key in FILE_FIELDS:
        return mapper.filename(value)
    if key in REF_FIELDS:
        return mapper.pseudonym("ref", value)
    if key in TEXT_FIELDS:
        return mapper.text(value)
    if isinstance(value, str):
        return mapper.text(value)
    return value


def collect_sensitive_values(value, values: dict[str, set[str]] | None = None, key: str = "") -> dict[str, set[str]]:
    values = values if values is not None else {}
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            collect_sensitive_values(child_value, values, child_key)
        return values
    if isinstance(value, list):
        for item in value:
            collect_sensitive_values(item, values, key)
        return values

    text = normalize_value(value)
    if not text:
        return values
    if key in PERSON_FIELDS or key == "attendees":
        add_value(values, "person", text)
    elif key in UNIT_FIELDS:
        add_value(values, "unit", text)
    elif key in COMPANY_FIELDS:
        add_value(values, "company", text)
    elif key in LOCATION_FIELDS:
        add_value(values, "location", text)
    elif key in FILE_FIELDS:
        add_value(values, "file", text)
    elif key in REF_FIELDS:
        add_value(values, "ref", text)
    return values


def add_value(values: dict[str, set[str]], kind: str, value: str) -> None:
    values.setdefault(kind, set()).add(value)


def normalize_value(value) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in MISSING_VALUES else text


def neutral_placeholder(kind: str) -> str:
    return {
        "person": "person",
        "unit": "unit",
        "company": "company",
        "location": "location",
        "file": "file",
        "ref": "reference",
        "email": "email",
        "phone": "phone",
        "id": "identifier",
    }.get(str(kind or "").lower(), "identifier")


def replace_pattern_tokens(text: str, mapper: Deidentifier, pattern: re.Pattern, kind: str, prefix: str) -> str:
    def repl(match):
        if kind == "phone" and sum(char.isdigit() for char in match.group(0)) < 9:
            return match.group(0)
        mapper.token(kind, match.group(0), prefix)
        return neutral_placeholder(kind)

    return pattern.sub(repl, text)


def write_mapping_records(records: list[dict]) -> None:
    mapping_path = str(getattr(settings, "DEIDENTIFICATION_MAPPING_FILE", "") or "").strip()
    if not mapping_path or not records:
        return

    destination = Path(mapping_path)
    if not destination.is_absolute():
        destination = settings.BASE_DIR / destination
    destination.parent.mkdir(parents=True, exist_ok=True)

    existing = {}
    if destination.exists():
        try:
            payload = json.loads(destination.read_text(encoding="utf-8"))
            for row in payload.get("records", []):
                existing[(row.get("kind"), row.get("original"))] = row
        except json.JSONDecodeError:
            existing = {}
    for row in records:
        existing[(row["kind"], row["original"])] = row

    output_records = sorted(existing.values(), key=lambda row: (row["kind"], row["original"]))
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "warning": "This file contains original sensitive values. Keep it separate from the de-identified database.",
        "record_count": len(output_records),
        "records": output_records,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
