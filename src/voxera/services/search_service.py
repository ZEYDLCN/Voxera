from dataclasses import dataclass
from uuid import UUID

from voxera.db.models import Review
from voxera.db.repositories.contracts import ReviewEmbeddingRepository
from voxera.services.embedding_service import EmbeddingModel

DEFAULT_SEARCH_LIMIT = 10


@dataclass(frozen=True, slots=True)
class SearchResult:
    review: Review
    similarity: float


async def semantic_search(
    *,
    embedding_repository: ReviewEmbeddingRepository,
    model: EmbeddingModel,
    product_id: UUID,
    query_text: str,
    model_version: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
) -> list[SearchResult]:
    """Query -> Embedding -> pgvector search -> Top-K reviews (spec section 20).

    No reranker yet (spec's hybrid-search/reranking stage): this returns pgvector's
    raw cosine-similarity ranking. See docs/ROADMAP.md Phase 4/6 for hybrid search and
    reranking as explicit follow-ups.
    """

    query_embedding = model.embed_many([query_text])[0]
    matches = await embedding_repository.search_similar(
        product_id,
        query_embedding,
        model_version=model_version,
        limit=limit,
    )
    return [SearchResult(review=review, similarity=similarity) for review, similarity in matches]
