# Maintainer Guide

This guide is for the next maintainer of the thesis retrieval system.

## System Purpose

The system supports structured document parsing and retrieval for enterprise meeting records. It combines document upload, meeting-minute parsing, keyword search, vector search, Neo4j graph retrieval, and GraphRAG question answering.

## Runtime Services

The Django app can start without every backend service, but feature completeness depends on these services:

- MongoDB: stores documents, meeting minutes, meeting items, click logs, feedback, and evaluation records.
- Neo4j: stores and queries graph entities and relationships.
- Qdrant: stores vector embeddings for semantic retrieval.
- Ollama: provides embedding and LLM inference calls.

Configure these services through `.env`. Use `.env.example` as the template.

## Main Pages

- `/documents/`: upload and manage source documents.
- `/meetings/`: browse parsed meeting minutes and meeting items.
- `/search/`: keyword, related-item, and related-meeting search workflows.
- `/graphrag/`: GraphRAG question answering and evaluation workflows.

## API Surface

Document APIs:

- `POST /api/documents/upload/`
- `GET /api/documents/`
- `POST /api/documents/<document_id>/parse-meeting-minutes/`
- `GET/DELETE /api/documents/<document_id>/`

Meeting APIs:

- `GET /api/meeting-minutes/`
- `GET /api/meeting-minutes/<meeting_id>/`
- `GET /api/meeting-items/`

Graph APIs:

- `POST /api/graph/build/`
- `POST /api/graph/keywords/extract/`
- `GET /api/graph/keyword/<keyword>/related/`
- `POST /api/graph/search/`
- `POST /api/graph/text2cypher/`
- `POST /api/graph/node/expand/`

Search APIs:

- `GET /api/search/meeting-minutes/`
- `POST /api/search/click/`
- `GET /api/search/related-meetings/<meeting_id>/`
- `GET /api/search/related-items/<item_id>/`
- `GET /api/search/stats/`

Vector APIs:

- `POST /api/vector/reindex/`
- `POST /api/vector/search/`

GraphRAG APIs:

- `POST /api/graphrag/ask/`
- `POST /api/graphrag/eval/seed/`
- `POST /api/graphrag/eval/run/`
- `POST /api/graphrag/eval/save/`

## Management Commands

- `python manage.py deidentify_data`: de-identify ingested data for privacy-sensitive handoff.
- `python manage.py repair_item_statuses`: repair item status fields.
- `python manage.py debug_item_status`: inspect item status issues.
- `python manage.py seed_graphrag_cases`: seed GraphRAG evaluation cases.
- `python manage.py eval_graphrag`: run GraphRAG evaluation.
- `python manage.py reset_ingested_data`: clear ingested data; use flags carefully.

## Code Areas

- `apps/documents`: upload, file validation, and document persistence.
- `apps/parser`: PDF text extraction and meeting-minute parsing.
- `apps/meetings`: meeting-minute and meeting-item read APIs.
- `apps/search`: keyword scoring, ranking, highlighting, feedback, and statistics.
- `apps/vector`: vector indexing and Qdrant search.
- `apps/graph`: Neo4j client, graph build/search, query planning, and text-to-Cypher.
- `apps/graphrag`: query routing, evidence selection, deterministic fallback, and evaluation.
- `apps/privacy`: de-identification logic and data reset utilities.

## Setup From a Clean Checkout

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`, then run:

```powershell
python manage.py check
python manage.py runserver
```

## Data and Archive Locations

The repository root should stay focused on the application. Local handoff artifacts are stored under `_handoff/`, which is ignored by Git.

- `_handoff/sample-data/`: prior PDFs and uploaded files.
- `_handoff/evaluation-results/`: experiment metrics and retrieval outputs.
- `_handoff/thesis-documents/`: thesis drafts and PDFs.
- `_handoff/presentations/`: presentation decks.
- `_handoff/work-archive/`: large scratch exports.
- `_handoff/reference-implementation/`: older standalone reference implementation.
- `_handoff/private-local/`: local secrets and de-identification mappings.

## Git Notes

The cleanup intentionally removes many previously tracked thesis artifacts, generated outputs, sample PDFs, and scratch files from the repository root. Review `git status` before committing.

The current working tree also had application code changes before cleanup in:

- `apps/graphrag/deterministic.py`
- `apps/graphrag/services.py`
- `apps/graphrag/tests.py`
- `apps/search/ranking.py`
- `apps/search/tests.py`

Review these application changes separately from the cleanup.
