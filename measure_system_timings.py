from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent


def setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def elapsed_call(callback, *args, **kwargs):
    started = time.perf_counter()
    result = callback(*args, **kwargs)
    return result, time.perf_counter() - started


def summarize(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "total_sec": 0, "avg_sec": 0, "min_sec": 0, "max_sec": 0, "median_sec": 0}
    return {
        "count": len(values),
        "total_sec": round(sum(values), 4),
        "avg_sec": round(statistics.mean(values), 4),
        "min_sec": round(min(values), 4),
        "max_sec": round(max(values), 4),
        "median_sec": round(statistics.median(values), 4),
    }


def measure_preprocessing() -> list[dict]:
    from django.conf import settings

    from apps.documents.mongo import get_documents_collection
    from apps.parser.meeting_minutes_parser import parse_meeting_minutes
    from apps.parser.pdf_text_extractor import PDFTextExtractor
    from apps.privacy.deidentification import deidentify_parsed_meeting_payload

    rows = []
    documents = list(
        get_documents_collection()
        .find({"file_ext": ".pdf", "is_deleted": False}, {"_id": 0})
        .sort("document_id", 1)
    )
    for document in documents:
        absolute_path = settings.UPLOAD_ROOT / document["stored_filename"]
        if not absolute_path.exists():
            absolute_path = settings.BASE_DIR / document["file_path"]
        row = {
            "document_id": document.get("document_id"),
            "original_filename": document.get("original_filename"),
            "stored_filename": document.get("stored_filename"),
            "status_before": document.get("status"),
            "page_count_before": document.get("page_count"),
        }
        if not absolute_path.exists():
            row.update({"status": "missing_file", "elapsed_sec": None, "item_count": 0})
            rows.append(row)
            continue

        started = time.perf_counter()
        payload = PDFTextExtractor(absolute_path).extract()
        parsed = parse_meeting_minutes(payload, document_id=document["document_id"])
        parsed = deidentify_parsed_meeting_payload(parsed)
        elapsed = time.perf_counter() - started
        row.update(
            {
                "status": parsed.get("status"),
                "page_count": payload.get("page_count"),
                "item_count": len(parsed.get("meeting_items") or []),
                "elapsed_sec": round(elapsed, 4),
            }
        )
        rows.append(row)
    return rows


def measure_graph_build() -> dict:
    from apps.graph.services import build_graph

    result, elapsed = elapsed_call(build_graph)
    payload = dict(result or {})
    payload["elapsed_sec"] = round(elapsed, 4)
    return payload


def load_query_cases() -> list[dict]:
    source = BASE / "vector_rag_18q_taper_0629.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    return [
        {"category": row.get("category"), "question": row.get("question")}
        for row in payload.get("rows", [])
        if row.get("question")
    ]


def measure_graphrag_queries(cases: list[dict]) -> list[dict]:
    from apps.graphrag.services import answer_question

    rows = []
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        error = ""
        payload = {}
        try:
            payload = answer_question(case["question"], limit="auto")
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        trace = payload.get("trace") or {}
        contexts = payload.get("contexts") or {}
        graph_context = contexts.get("graph") or {}
        row = {
            "index": index,
            "category": case.get("category"),
            "question": case.get("question"),
            "elapsed_sec": round(elapsed, 4),
            "source_count": len(payload.get("sources") or []),
            "structured_count": len(contexts.get("structured") or []),
            "graph_path_count": len(graph_context.get("paths") or []),
            "semantic_count": len(contexts.get("semantic") or []),
            "query_type": ((payload.get("query_route") or {}).get("query_type")),
            "limit_mode": payload.get("limit_mode"),
            "warning_count": len(payload.get("warnings") or []),
            "error": error,
        }
        if trace.get("answer_claims"):
            row["claim_count"] = len((trace.get("answer_claims") or {}).get("evidence_ids") or [])
        else:
            row["claim_count"] = 0
        rows.append(row)
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_existing_report() -> dict:
    path = BASE / "system_timing_measurements_0629.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "measurement_definition": {
            "preprocessing": "Non-destructive PDF text extraction, meeting-minutes parsing, de-identification transform; MongoDB write-back is excluded.",
            "knowledge_graph_build": "build_graph(): MongoDB meeting records to Neo4j graph construction using current database contents.",
            "query_response": "answer_question() end-to-end GraphRAG response time for the same 18 evaluation questions.",
        },
        "summary": {},
        "preprocessing": [],
        "knowledge_graph_build": {},
        "query_response": [],
    }


def save_report(report: dict) -> None:
    json_path = BASE / "system_timing_measurements_0629.json"
    csv_pre = BASE / "system_timing_preprocessing_0629.csv"
    csv_query = BASE / "system_timing_graphrag_queries_0629.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(csv_pre, report.get("preprocessing") or [])
    write_csv(csv_query, report.get("query_response") or [])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stage",
        choices=["all", "preprocess", "graph", "query"],
        default="all",
        help="Measurement stage to run.",
    )
    parser.add_argument("--query-start", type=int, default=1, help="1-based query index to start from.")
    parser.add_argument("--query-end", type=int, default=0, help="1-based query index to end at; 0 means all.")
    args = parser.parse_args()

    setup_django()
    report = load_existing_report()

    if args.stage in {"all", "preprocess"}:
        print("Measuring preprocessing...", flush=True)
        report["preprocessing"] = measure_preprocessing()
        report["summary"]["preprocessing"] = summarize(
            [row["elapsed_sec"] for row in report["preprocessing"] if isinstance(row.get("elapsed_sec"), (int, float))]
        )
        save_report(report)

    if args.stage in {"all", "graph"}:
        print("Measuring knowledge graph build...", flush=True)
        graph_build = measure_graph_build()
        report["knowledge_graph_build"] = graph_build
        report["summary"]["knowledge_graph_build"] = {
            "elapsed_sec": graph_build.get("elapsed_sec"),
            "meeting_count": graph_build.get("meeting_count"),
            "item_count": graph_build.get("item_count"),
            "neo4j_available": graph_build.get("neo4j_available"),
        }
        save_report(report)

    if args.stage in {"all", "query"}:
        cases = load_query_cases()
        start = max(args.query_start, 1)
        end = args.query_end if args.query_end else len(cases)
        selected = cases[start - 1 : end]
        print(f"Measuring GraphRAG queries {start}-{end}...", flush=True)
        rows = measure_graphrag_queries(selected)
        for offset, row in enumerate(rows, start=start):
            row["index"] = offset
        existing = [row for row in report.get("query_response", []) if not (start <= int(row.get("index", 0)) <= end)]
        report["query_response"] = sorted([*existing, *rows], key=lambda row: int(row.get("index", 0)))
        report["summary"]["query_response"] = summarize(
            [row["elapsed_sec"] for row in report["query_response"] if not row.get("error")]
        )
        save_report(report)

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print("system_timing_measurements_0629.json")
    print("system_timing_preprocessing_0629.csv")
    print("system_timing_graphrag_queries_0629.csv")


if __name__ == "__main__":
    main()
