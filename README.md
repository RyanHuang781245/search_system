# Search System Backend

Django backend for document upload, meeting parsing, keyword/vector search, graph search, and GraphRAG retrieval.

## Project Layout

- `apps/`: Django apps for documents, meetings, graph, search, vector, GraphRAG, privacy, and parsing.
- `config/`: Django settings and URL routing.
- `templates/`: HTML pages for the console UI.
- `static/`: JavaScript and CSS assets.
- `docs/`: handoff notes and system documentation.
- `_handoff/`: archived thesis, presentation, experiment, sample data, reference code, and one-off research artifacts.
- `uploads/`: runtime uploads. Django recreates this directory on startup; files in it are ignored.
- `work/`: local export/scratch output. This directory is ignored.

## Setup

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` for MongoDB, Neo4j, Qdrant, and Ollama connection settings.

## Run

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

Main pages:

- `/documents/`
- `/meetings/`
- `/search/`
- `/graphrag/`

## Tests

```powershell
python manage.py test
```

Some integration paths require MongoDB, Neo4j, Qdrant, and Ollama services to be available.

## Archived Material

Sample PDFs and previous uploaded files are under `_handoff/sample-data/`. The older standalone Qdrant/Neo4j/Ollama reference implementation is under `_handoff/reference-implementation/`.

More detailed maintainer notes are in `docs/handoff.md` and `docs/maintainer_guide.md`. Use `HANDOFF_CHECKLIST.md` before handing the system to another person.
