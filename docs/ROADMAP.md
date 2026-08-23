# Voxera implementation roadmap

Each phase must leave the main branch deployable and includes explicit exit criteria.

## Phase 1 — Platform foundation

- FastAPI application factory and versioned API router
- Typed settings loaded from environment variables
- Structured application logging and request IDs
- Liveness/readiness endpoints
- PostgreSQL/pgvector, Redis and MinIO development services
- Unit tests, linting and type-check configuration

Exit: the application starts locally and health tests pass.

## Phase 2 — Data foundation

- Async SQLAlchemy engine and transaction management
- Tenant-aware core tables and PostgreSQL row-level security
- Alembic migrations, UUIDv7-style identifiers and audit fields
- Repository contracts and integration tests against PostgreSQL

Exit: organizations, products, sources and reviews can be persisted without tenant leakage.

## Phase 3 — Ingestion and preprocessing

- [x] CSV/JSON/JSONL schemas and streaming parsers (`voxera.ingestion`)
- [x] Language detection, text normalization, PII masking and deduplication
      (`voxera.preprocessing`), wired through `POST /reviews/import`
      (`voxera.services.import_service`)
- [x] Object-storage upload flow (`voxera.storage.S3ObjectStorage`, MinIO/S3-compatible)
- [x] Import jobs, Celery workers and retries (`apps.worker`, `import_jobs` table,
      `POST /reviews/import-jobs` + `GET /reviews/import-jobs/{id}`). A periodic
      reconciliation task stands in for a generic transactional outbox -- see the
      `ImportJob.status`/`dispatched_at` design note in
      `voxera.services.import_job_service`.

Exit: a large CSV import completes asynchronously and produces normalized reviews. Met:
upload -> `import_jobs` row -> Celery worker -> `ReviewImportService` -> job status +
summary, with exponential-backoff retries and reconciliation for lost dispatches or
crashed workers.

## Phase 4 — Core ML and search

- Versioned sentiment baseline and evaluation report
- Batch embedding pipeline and pgvector HNSW index
- Semantic search with product/date/source filters
- Golden datasets and regression checks

Exit: every eligible review has reproducible analysis and semantic search meets Recall@K target.

## Phase 5 — Topic intelligence

- HDBSCAN discovery and online topic assignment
- Stable canonical topic mapping across analysis runs
- Representative review selection and structured topic naming
- Daily/hourly topic aggregates and analytics endpoints

Exit: topics remain traceable across re-clustering and dashboard metrics reconcile with raw data.

## Phase 6 — Product experience and RAG

- Next.js dashboard and review explorer
- PostgreSQL full-text plus vector hybrid retrieval
- Optional reranker behind a feature flag
- Evidence-grounded Ask Voxera with citations and verification

Exit: unsupported claims are rejected and every analytical answer contains valid evidence.

## Phase 7 — Advanced intelligence

- Trend and anomaly detection
- Emerging issue detection
- Release impact comparison
- Alert lifecycle and webhook delivery

Exit: algorithms pass backtests and alerts satisfy precision thresholds.

## Phase 8 — Production hardening

- OpenTelemetry, metrics, dashboards and alerting
- Threat model, retention controls and security tests
- Load/cost tests, model rollback and disaster recovery
- CI/CD, staging and controlled production rollout

Exit: service-level objectives, recovery procedures and operational ownership are documented.

