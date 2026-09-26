# Bard

Bard is a context-aware Dungeon Master assistant for D&D sessions.

The first version is a Python/FastAPI backend with PostgreSQL. The domain model
is authoritative; AI, retrieval, speech-to-text, and embeddings are supporting
services and must not become the source of truth.

## Development

```bash
docker compose up -d db
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

Open `http://localhost:8000/docs` for the API documentation and
`devtools/test_console/index.html` for the simple browser test console.

## Repository rules

Read `AGENTS.md` before making changes. Architecture, schema, technology,
phase, and documentation decisions are recorded under `.developer/`.
