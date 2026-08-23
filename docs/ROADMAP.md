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

- [x] Versioned sentiment baseline and evaluation report (`voxera.ml.sentiment`:
      TF-IDF + Logistic Regression, `evaluate_model`, `SentimentModelRegistry` on top
      of object storage; `python -m voxera.ml.sentiment.train` trains, evaluates and
      publishes a version)
- [x] Golden dataset and regression check (`data/sentiment/{train,golden}.csv` --
      small bootstrap set, see `data/sentiment/README.md` -- and
      `tests/evaluation/test_sentiment_golden.py` asserting a macro-F1 floor)
- [x] Reproducible per-review analysis (`review_sentiments` table keyed by
      (review_id, model_version); `POST /analytics/sentiment/analyze` and
      `GET /analytics/sentiment`; `voxera.services.sentiment_analysis_service`)
- [ ] Transformer-based sentiment model for comparison against the baseline (spec's
      model-comparison ladder: TF-IDF+LogReg -> TF-IDF+SVM -> Transformer)
- [x] Batch embedding pipeline (`voxera.embeddings`: TF-IDF + Truncated SVD/LSA,
      `python -m voxera.embeddings.train` fits on a tenant's own reviews and publishes
      via `EmbeddingModelRegistry`) and pgvector HNSW index
      (`review_embeddings.embedding vector(256)`, `USING hnsw (... vector_cosine_ops)`)
- [x] Semantic search (`GET /reviews/search`: query -> embed -> pgvector cosine search
      -> top-K, `voxera.services.search_service`), scoped by product and model version
      -- date/source filters still open
- [ ] Multilingual sentence-transformer embedding model (multilingual-e5/BGE) to
      replace/compare against the LSA baseline -- **blocked in this sandbox**: the
      network proxy only reaches PyPI, and PyPI's default Linux `torch` wheel pulls a
      multi-GB CUDA/GPU toolkit with no CPU-only wheel reachable from here, so
      `sentence-transformers` could not be installed. `EmbeddingModel.embed_many` is
      already the contract such a model would implement -- swapping it in needs no
      redesign, just an environment with PyPI's CPU-only torch index reachable (or a
      pre-built wheel supplied another way) plus a new pgvector column width if the
      model's native dimensionality differs from 256.
- [ ] Hybrid (BM25 + vector) search and reranking (spec sections 21-22)
- [ ] Retrieval golden dataset and Precision@K/Recall@K/MRR/NDCG regression checks

Exit: every eligible review has reproducible analysis and semantic search meets Recall@K
target. Sentiment analysis and embeddings/search are both idempotent, versioned and
working end-to-end today (verified against a mocked S3 plus SQL-compile checks against
a real pgvector query shape). Not yet met: no Recall@K target has been measured, because
there is no retrieval golden dataset yet to measure it against -- see the checklist above.

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

