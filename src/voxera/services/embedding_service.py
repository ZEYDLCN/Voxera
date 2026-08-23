from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from voxera.db.repositories.contracts import (
    ReviewEmbeddingCreate,
    ReviewEmbeddingRepository,
    ReviewRepository,
)

DEFAULT_EMBEDDING_BATCH_LIMIT = 500


class EmbeddingModel(Protocol):
    """Anything that turns text into fixed-width vectors.

    `TfidfSvdEmbeddingModel` implements this today; a transformer-based model (the
    next rung of the spec's embedding ladder -- see docs/ROADMAP.md) can be swapped in
    later without this service, or semantic search built on top of it, changing.
    """

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(slots=True)
class EmbeddingSummary:
    embedded: int = 0


async def embed_pending_reviews(
    *,
    review_repository: ReviewRepository,
    embedding_repository: ReviewEmbeddingRepository,
    model: EmbeddingModel,
    product_id: UUID,
    model_name: str,
    model_version: str,
    limit: int = DEFAULT_EMBEDDING_BATCH_LIMIT,
) -> EmbeddingSummary:
    """Embed every review for `product_id` with no vector yet for `model_version`.

    Idempotent and safely re-runnable for the same reasons as
    `voxera.services.sentiment_analysis_service.analyze_pending_reviews`:
    `ReviewRepository.list_for_embedding` already excludes reviews that have a vector
    for this exact model version.
    """

    reviews = await review_repository.list_for_embedding(
        product_id,
        model_version=model_version,
        limit=limit,
    )
    if not reviews:
        return EmbeddingSummary()

    vectors = model.embed_many([review.text_normalized for review in reviews])

    summary = EmbeddingSummary()
    for review, vector in zip(reviews, vectors, strict=True):
        await embedding_repository.upsert(
            ReviewEmbeddingCreate(
                product_id=product_id,
                review_id=review.id,
                model_name=model_name,
                model_version=model_version,
                embedding=vector,
            )
        )
        summary.embedded += 1

    return summary
