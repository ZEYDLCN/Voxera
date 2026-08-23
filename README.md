# Voxera

Voxera turns large-scale customer feedback into actionable product intelligence.
The application combines deterministic analytics, classical ML, embeddings, topic
discovery and evidence-grounded LLM workflows.

## Current status

Phases 1-3 are complete and Phase 4 is in progress. The repository contains the FastAPI
platform foundation, a tenant-aware async SQLAlchemy data layer with Alembic migrations
and PostgreSQL RLS policies, and the full ingestion pipeline: CSV/JSON/JSONL parsing, a
deterministic preprocessing pipeline (normalization, PII masking, language detection,
hashing), content-hash deduplication, a synchronous `POST /reviews/import` endpoint for
small batches, and an asynchronous `POST /reviews/import-jobs` path that uploads to
MinIO/S3 and processes on a Celery worker with retries and a periodic reconciliation
sweep standing in for a transactional outbox.

Phase 4 so far: a TF-IDF + Logistic Regression sentiment baseline (`voxera.ml.sentiment`)
with a training/evaluation CLI, a versioned model registry on top of object storage, a
`review_sentiments` table keyed by (review, model version) for reproducible re-analysis,
and `POST /analytics/sentiment/analyze` + `GET /analytics/sentiment` endpoints. Still
open in Phase 4: a transformer-based sentiment model for comparison, the embedding
pipeline, pgvector indexing and semantic search, and a proper golden evaluation dataset
(the bundled one is a small bootstrap set -- see `data/sentiment/README.md`).

## Development phases

1. **Platform foundation** — API skeleton, configuration, local infrastructure and CI checks.
2. **Data foundation** — tenant-aware PostgreSQL schema, migrations and repositories.
3. **Ingestion** — CSV/JSON import, object storage, background jobs and preprocessing.
4. **Core ML** — sentiment baseline, embeddings, semantic search and evaluation datasets.
5. **Topic intelligence** — clustering, stable topics, representatives and analytics.
6. **Product experience** — dashboard, hybrid search and evidence-grounded Ask Voxera.
7. **Advanced intelligence** — trends, anomalies, release impact and alerts.
8. **Production hardening** — observability, security, load tests, CI/CD and deployment.

Detailed exit criteria are documented in [docs/ROADMAP.md](docs/ROADMAP.md).

## Local setup

Requirements:

- Python 3.12+
- Docker with Compose

Create an environment and install the development dependencies:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Start the API directly:

```bash
uvicorn apps.api.main:app --reload
```

Or start the API, Celery worker/beat and backing services (Postgres, Redis, MinIO):

```bash
docker compose up --build
```

Apply the database schema with the admin connection after PostgreSQL is ready. The API
uses a separate non-owner role so row-level security cannot be bypassed:

```bash
alembic upgrade head
```

Useful URLs:

- API documentation: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`
- MinIO console: `http://localhost:9001`

## Importing reviews

`POST /reviews/import` accepts a CSV, JSON array or JSON Lines file for an existing
organization/product/source and returns a per-row summary (imported, duplicates,
rejected, with reasons):

```bash
curl -X POST "http://localhost:8000/reviews/import" \
  -F "organization_id=<uuid>" \
  -F "product_id=<uuid>" \
  -F "source_id=<uuid>" \
  -F "format=csv" \
  -F "file=@reviews.csv"
```

Each row is validated against a unified schema (`text`, `occurred_at`, optional
`external_id`/`rating`/`language`/`attributes`), then run through the deterministic
preprocessing pipeline (HTML/URL stripping, whitespace normalization, PII masking,
language detection, SHA-256 content hashing) before being deduplicated and persisted.
A malformed row never aborts the rest of the file.

For large files, `POST /reviews/import-jobs` uploads the file to object storage,
records a job row and returns `202 Accepted` immediately; a Celery worker downloads,
preprocesses and persists reviews off the request path using the exact same pipeline:

```bash
curl -X POST "http://localhost:8000/reviews/import-jobs" \
  -F "organization_id=<uuid>" \
  -F "product_id=<uuid>" \
  -F "source_id=<uuid>" \
  -F "format=csv" \
  -F "file=@large-export.csv"
# => {"id": "...", "status": "pending", ...}

curl "http://localhost:8000/reviews/import-jobs/<job id>?organization_id=<uuid>"
# => {"id": "...", "status": "succeeded", "total_rows": 42000, "imported": 41988, ...}
```

A failed attempt retries with exponential backoff (up to 5 attempts). A periodic
reconciliation task (Celery beat, every 5 minutes) re-dispatches any job whose direct
enqueue was never confirmed or whose worker died mid-processing, and abandons a job
that has exhausted its attempt budget -- see
`voxera.services.import_job_service.reconcile_organization_import_jobs`.

## Sentiment analysis

Train and publish the TF-IDF + Logistic Regression baseline (object storage must be
reachable; set `VOXERA_OBJECT_STORAGE_*` or run via `docker compose`):

```bash
python -m voxera.ml.sentiment.train --version tfidf-logreg-2026-08-23
# prints the evaluation report, then publishes model.joblib + evaluation.json to
# models/sentiment/<version>/ in object storage. Use --dry-run to just print the report.
```

Point the API at that version and restart it:

```bash
VOXERA_SENTIMENT_MODEL_VERSION=tfidf-logreg-2026-08-23
```

Then run and read sentiment:

```bash
curl -X POST "http://localhost:8000/analytics/sentiment/analyze?organization_id=<uuid>&product_id=<uuid>"
# => {"analyzed": 41988, "model_version": "tfidf-logreg-2026-08-23",
#     "label_counts": {"positive": 25600, "negative": 9200, "neutral": 7188}}

curl "http://localhost:8000/analytics/sentiment?organization_id=<uuid>&product_id=<uuid>"
# => {"total": 41988, "counts": {...}, "percentages": {"positive": 61.0, ...}}
```

Analysis is keyed by (review, model_version), not by overwriting a single column: a
review already scored under the pinned version is skipped on the next call (safe to
call repeatedly, e.g. after every import), and publishing a new model version
re-analyzes everything under that version without losing prior results. See
`voxera.services.sentiment_analysis_service` and `docs/ROADMAP.md` Phase 4.

The bundled `data/sentiment/{train,golden}.csv` are a small, hand-labeled bilingual
bootstrap dataset, not production training data -- see `data/sentiment/README.md`.
`tests/evaluation/test_sentiment_golden.py` is the regression test that guards the
baseline's F1 on the golden set; run it after any model or data change.

Run quality checks:

```bash
ruff check .
mypy src
pytest --cov
```

PostgreSQL integration tests are opt-in and refuse to run unless the database name ends
with `_test`:

```bash
VOXERA_TEST_DATABASE_URL=postgresql+asyncpg://app:pass@localhost/voxera_test \
VOXERA_TEST_DATABASE_ADMIN_URL=postgresql+asyncpg://admin:pass@localhost/voxera_test \
pytest -m integration
```

Copy `.env.example` to `.env` for local overrides. Never use the example credentials in
a deployed environment.
