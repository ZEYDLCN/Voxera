from uuid import UUID, uuid4

import pytest
from tests.unit.fakes import (
    FakeReviewEmbeddingRepository,
    FakeReviewRepository,
    make_review,
)

from voxera.services.embedding_service import embed_pending_reviews
from voxera.services.search_service import semantic_search


class FakeEmbeddingModel:
    """Deterministic stand-in for `EmbeddingModel`: one-hot-ish vector by keyword."""

    _VOCAB = ("login", "payment", "delivery")

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        lowered = text.lower()
        return [1.0 if word in lowered else 0.0 for word in self._VOCAB]


@pytest.mark.asyncio
async def test_embed_pending_reviews_embeds_and_persists_every_review() -> None:
    product_id = uuid4()
    embedded_pairs: set[tuple[UUID, str]] = set()
    reviews = [
        make_review(product_id=product_id, text_normalized="login is broken"),
        make_review(product_id=product_id, text_normalized="payment failed"),
    ]
    review_repository = FakeReviewRepository(reviews=reviews, embedded_pairs=embedded_pairs)
    embedding_repository = FakeReviewEmbeddingRepository(embedded_pairs=embedded_pairs)

    summary = await embed_pending_reviews(
        review_repository=review_repository,
        embedding_repository=embedding_repository,
        model=FakeEmbeddingModel(),
        product_id=product_id,
        model_name="tfidf-svd",
        model_version="v1",
    )

    assert summary.embedded == 2
    assert len(embedding_repository.records) == 2


@pytest.mark.asyncio
async def test_embed_pending_reviews_is_idempotent_for_the_same_model_version() -> None:
    product_id = uuid4()
    embedded_pairs: set[tuple[UUID, str]] = set()
    reviews = [make_review(product_id=product_id, text_normalized="login is broken")]
    review_repository = FakeReviewRepository(reviews=reviews, embedded_pairs=embedded_pairs)
    embedding_repository = FakeReviewEmbeddingRepository(embedded_pairs=embedded_pairs)
    model = FakeEmbeddingModel()

    first = await embed_pending_reviews(
        review_repository=review_repository,
        embedding_repository=embedding_repository,
        model=model,
        product_id=product_id,
        model_name="tfidf-svd",
        model_version="v1",
    )
    second = await embed_pending_reviews(
        review_repository=review_repository,
        embedding_repository=embedding_repository,
        model=model,
        product_id=product_id,
        model_name="tfidf-svd",
        model_version="v1",
    )

    assert first.embedded == 1
    assert second.embedded == 0


@pytest.mark.asyncio
async def test_embed_pending_reviews_handles_no_pending_reviews() -> None:
    product_id = uuid4()
    review_repository = FakeReviewRepository(reviews=[])
    embedding_repository = FakeReviewEmbeddingRepository()

    summary = await embed_pending_reviews(
        review_repository=review_repository,
        embedding_repository=embedding_repository,
        model=FakeEmbeddingModel(),
        product_id=product_id,
        model_name="tfidf-svd",
        model_version="v1",
    )

    assert summary.embedded == 0


@pytest.mark.asyncio
async def test_semantic_search_ranks_matching_reviews_first() -> None:
    product_id = uuid4()
    reviews = [
        make_review(product_id=product_id, text_normalized="login is broken again"),
        make_review(product_id=product_id, text_normalized="payment keeps failing"),
        make_review(product_id=product_id, text_normalized="delivery was late"),
    ]
    reviews_by_id = {review.id: review for review in reviews}
    review_repository = FakeReviewRepository(reviews=reviews)
    embedding_repository = FakeReviewEmbeddingRepository(reviews_by_id=reviews_by_id)
    model = FakeEmbeddingModel()

    await embed_pending_reviews(
        review_repository=review_repository,
        embedding_repository=embedding_repository,
        model=model,
        product_id=product_id,
        model_name="tfidf-svd",
        model_version="v1",
    )

    results = await semantic_search(
        embedding_repository=embedding_repository,
        model=model,
        product_id=product_id,
        query_text="I can't login to my account",
        model_version="v1",
    )

    assert results[0].review.text_normalized == "login is broken again"
    assert results[0].similarity == pytest.approx(1.0)
    assert results[0].similarity > results[-1].similarity


@pytest.mark.asyncio
async def test_semantic_search_returns_empty_list_when_nothing_is_embedded() -> None:
    embedding_repository = FakeReviewEmbeddingRepository()

    results = await semantic_search(
        embedding_repository=embedding_repository,
        model=FakeEmbeddingModel(),
        product_id=uuid4(),
        query_text="anything",
        model_version="v1",
    )

    assert results == []
