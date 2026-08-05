# Handoff Checklist

Use this checklist before giving the system to the next maintainer.

## Repository

- [ ] Confirm the root directory contains only source code, configuration, docs, and `_handoff/`.
- [ ] Confirm `_handoff/` is present in the local folder if handing over by zip or external drive.
- [ ] Confirm `_handoff/private-local/` is removed or intentionally shared through a secure channel.
- [ ] Review `git status` and separate cleanup changes from application code changes.
- [ ] Decide whether to commit the cleanup deletions of previously tracked thesis/generated artifacts.

## Environment

- [ ] Create `.env` from `.env.example`.
- [ ] Fill MongoDB connection settings.
- [ ] Fill Neo4j connection settings.
- [ ] Fill Qdrant connection settings.
- [ ] Fill Ollama host, port, embedding model, and inference model.
- [ ] Rebuild `.venv/` with `pip install -r requirements.txt`.

## Verification

- [ ] Run `python manage.py check`.
- [ ] Run `python manage.py test`.
- [ ] Start the app with `python manage.py runserver`.
- [ ] Open `/documents/`, `/meetings/`, `/search/`, and `/graphrag/`.
- [ ] Upload or load one sample document from `_handoff/sample-data/pdf/`.
- [ ] Verify search, vector search, graph search, and GraphRAG only after their external services are running.

## Data

- [ ] Confirm whether MongoDB data should be exported separately.
- [ ] Confirm whether Neo4j graph data should be exported separately.
- [ ] Confirm whether Qdrant collection data should be exported separately.
- [ ] Confirm whether Ollama model names in `.env.example` match the target machine.
- [ ] Confirm de-identification mapping files are handled securely.

## Handoff Explanation

- [ ] Point the next maintainer to `README.md`.
- [ ] Point the next maintainer to `docs/handoff.md`.
- [ ] Point the next maintainer to `docs/maintainer_guide.md`.
- [ ] Explain that `_handoff/` is local archive material and is ignored by Git.
- [ ] Explain which code changes were already in progress before cleanup.
