# Handoff Notes

## What Was Cleaned

The repository root was reduced to source code, configuration, and handoff entry points. Thesis papers, slides, experiment outputs, and one-off helper scripts were moved into `_handoff/`.

Removed local-only files:

- Office lock files matching `~$*`
- Python bytecode cache directories named `__pycache__`

The local virtual environment `.venv/` is ignored. If Windows still has `.venv\\Scripts\\python.exe` locked, close any running Python process and remove `.venv/` manually.

The original local `.env` was moved to `_handoff/private-local/.env`. Create a fresh root `.env` from `.env.example` when setting up a new environment.

## Handoff Archive

- `_handoff/thesis-documents/`: thesis drafts, exported PDFs, and document backups.
- `_handoff/presentations/`: presentation decks and slide folders.
- `_handoff/evaluation-results/`: retrieval metrics, timing results, baseline outputs, and generated figures.
- `_handoff/research-scripts/`: one-off experiment and thesis helper scripts.
- `_handoff/temp-review/`: temporary text extraction, notes, and review artifacts.
- `_handoff/sample-data/`: local sample PDFs and prior uploaded files.
- `_handoff/reference-implementation/`: older standalone Qdrant/Neo4j/Ollama reference implementation.
- `_handoff/work-archive/`: previous slide exports, image extraction output, and other scratch working files.
- `_handoff/private-local/`: local privacy/de-identification mappings. This folder is ignored by Git.

## Runtime Dependencies

The app expects these external services depending on the feature:

- MongoDB: document and meeting data.
- Neo4j: graph data and Cypher queries.
- Qdrant: vector retrieval.
- Ollama: embedding and LLM calls.

Use `.env.example` as the starting point for required environment variables.

## Source Code Areas

- `apps/documents`: upload and document operations.
- `apps/meetings`: meeting record access.
- `apps/graph`: graph retrieval, Neo4j access, query planning, and de-identification commands.
- `apps/search`: keyword search, ranking, feedback, and highlighting.
- `apps/vector`: vector retrieval.
- `apps/graphrag`: GraphRAG routing, deterministic logic, evaluation, and APIs.
- `apps/privacy`: de-identification utilities.
- `apps/parser`: PDF and meeting-minute parsing helpers.

## Notes for the Next Maintainer

The working tree already had uncommitted application code changes before cleanup. Review `git status` and `git diff` before committing.

Start with these files:

- `README.md`: quick setup and run instructions.
- `docs/maintainer_guide.md`: system purpose, API surface, commands, and code ownership map.
- `HANDOFF_CHECKLIST.md`: final handoff checklist.

Verification note: if `.venv/` only contains `Scripts/python.exe` and `python manage.py check` reports `No pyvenv.cfg file`, remove the broken `.venv/` after closing running Python processes, then rebuild it from `requirements.txt`.
