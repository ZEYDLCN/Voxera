from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool

from voxera.db import Database
from voxera.db.repositories.sqlalchemy import SqlAlchemyReviewEmbeddingRepository
from voxera.embeddings.registry import EmbeddingModelRegistry
from voxera.services.search_service import semantic_search

router = APIRouter()


class SearchResultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: UUID
    text_redacted: str
    language: str
    rating: int | None
    occurred_at: datetime
    similarity: float


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    model_version: str
    results: list[SearchResultResponse]


@router.get("/search", response_model=SearchResponse)
async def search_reviews(
    request: Request,
    organization_id: UUID,
    product_id: UUID,
    query: str,
    limit: int = 10,
) -> SearchResponse:
    """Query -> embedding -> pgvector cosine search -> top-K reviews (spec section 20).

    Requires reviews for the product to have been embedded first via
    `POST /analytics/embeddings/generate` under the same pinned model version.
    """

    model_version = request.app.state.settings.embedding_model_version
    if not model_version:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "no embedding model version is configured (VOXERA_EMBEDDING_MODEL_VERSION)",
        )

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
        results = await semantic_search(
            embedding_repository=SqlAlchemyReviewEmbeddingRepository(session, organization_id),
            model=model,
            product_id=product_id,
            query_text=query,
            model_version=model_version,
            limit=limit,
        )

    return SearchResponse(
        query=query,
        model_version=model_version,
        results=[
            SearchResultResponse(
                review_id=result.review.id,
                text_redacted=result.review.text_redacted,
                language=result.review.language,
                rating=result.review.rating,
                occurred_at=result.review.occurred_at,
                similarity=result.similarity,
            )
            for result in results
        ],
    )
