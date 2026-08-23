from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from voxera.db import Database
from voxera.db.repositories.sqlalchemy import (
    SqlAlchemyReviewEmbeddingRepository,
    SqlAlchemyReviewRepository,
    SqlAlchemyReviewSentimentRepository,
)
from voxera.embeddings.registry import EmbeddingModelRegistry
from voxera.ml.sentiment.registry import SentimentModelRegistry
from voxera.services.embedding_service import embed_pending_reviews
from voxera.services.sentiment_analysis_service import analyze_pending_reviews

router = APIRouter()

SENTIMENT_MODEL_NAME = "tfidf-logreg"
EMBEDDING_MODEL_NAME = "tfidf-svd"


class SentimentAnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyzed: int
    model_version: str
    label_counts: dict[str, int]


class SentimentDistributionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    model_version: str
    total: int
    counts: dict[str, int]
    percentages: dict[str, float]


class EmbeddingGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    embedded: int
    model_version: str


def _require_model_version(request: Request) -> str:
    version = request.app.state.settings.sentiment_model_version
    if not version:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no sentiment model version is configured (VOXERA_SENTIMENT_MODEL_VERSION)",
        )
    return str(version)


def _require_embedding_model_version(request: Request) -> str:
    version = request.app.state.settings.embedding_model_version
    if not version:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no embedding model version is configured (VOXERA_EMBEDDING_MODEL_VERSION)",
        )
    return str(version)


@router.post("/sentiment/analyze", response_model=SentimentAnalyzeResponse)
async def analyze_sentiment(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    limit: int = 500,
) -> SentimentAnalyzeResponse:
    """Score every not-yet-analyzed review for a product with the pinned model
    version. Synchronous for now (MVP), mirroring `POST /reviews/import` -- a large
    backlog should move to a Celery task the same way ingestion did.
    """

    model_version = _require_model_version(request)
    registry = SentimentModelRegistry(request.app.state.object_storage)
    try:
        model = await run_in_threadpool(registry.load, model_version)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"sentiment model version {model_version!r} could not be loaded",
        ) from exc

    database: Database = request.app.state.database
    async with database.session(organization_id=organization_id) as session:
        summary = await analyze_pending_reviews(
            review_repository=SqlAlchemyReviewRepository(session, organization_id),
            sentiment_repository=SqlAlchemyReviewSentimentRepository(session, organization_id),
            analyzer=model,
            product_id=product_id,
            model_name=SENTIMENT_MODEL_NAME,
            model_version=model_version,
            limit=limit,
        )

    return SentimentAnalyzeResponse(
        analyzed=summary.analyzed,
        model_version=model_version,
        label_counts=summary.label_counts,
    )


@router.get("/sentiment", response_model=SentimentDistributionResponse)
async def get_sentiment_distribution(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
) -> SentimentDistributionResponse:
    model_version = _require_model_version(request)

    database: Database = request.app.state.database
    async with database.session(organization_id=organization_id) as session:
        sentiments = SqlAlchemyReviewSentimentRepository(session, organization_id)
        counts = await sentiments.aggregate_distribution(product_id, model_version=model_version)

    counts_by_value = {label.value: count for label, count in counts.items()}
    total = sum(counts_by_value.values())
    percentages = (
        {label: round(count / total * 100, 1) for label, count in counts_by_value.items()}
        if total
        else {}
    )

    return SentimentDistributionResponse(
        product_id=product_id,
        model_version=model_version,
        total=total,
        counts=counts_by_value,
        percentages=percentages,
    )


@router.post("/embeddings/generate", response_model=EmbeddingGenerateResponse)
async def generate_embeddings(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    limit: int = 500,
) -> EmbeddingGenerateResponse:
    """Embed every not-yet-embedded review for a product with the pinned model
    version. Synchronous for now (MVP), same tradeoff as `analyze_sentiment`."""

    model_version = _require_embedding_model_version(request)
    registry = EmbeddingModelRegistry(request.app.state.object_storage)
    try:
        model = await run_in_threadpool(registry.load, model_version)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"embedding model version {model_version!r} could not be loaded",
        ) from exc

    database: Database = request.app.state.database
    async with database.session(organization_id=organization_id) as session:
        summary = await embed_pending_reviews(
            review_repository=SqlAlchemyReviewRepository(session, organization_id),
            embedding_repository=SqlAlchemyReviewEmbeddingRepository(session, organization_id),
            model=model,
            product_id=product_id,
            model_name=EMBEDDING_MODEL_NAME,
            model_version=model_version,
            limit=limit,
        )

    return EmbeddingGenerateResponse(embedded=summary.embedded, model_version=model_version)
