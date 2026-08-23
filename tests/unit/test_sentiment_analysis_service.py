from uuid import UUID, uuid4

import pytest
from tests.unit.fakes import FakeReviewRepository, FakeReviewSentimentRepository, make_review

from voxera.db.models.enums import ReviewStatus, SentimentLabel
from voxera.ml.sentiment.model import SentimentPrediction
from voxera.services.sentiment_analysis_service import analyze_pending_reviews


class FakeAnalyzer:
    """Deterministic stand-in for `SentimentAnalyzer`: label chosen by text prefix."""

    def predict_many(self, texts: list[str]) -> list[SentimentPrediction]:
        predictions = []
        for text in texts:
            if text.startswith("neg"):
                predictions.append(SentimentPrediction(label="negative", score=0.9))
            elif text.startswith("neu"):
                predictions.append(SentimentPrediction(label="neutral", score=0.7))
            else:
                predictions.append(SentimentPrediction(label="positive", score=0.8))
        return predictions


@pytest.mark.asyncio
async def test_analyze_pending_reviews_scores_and_persists_every_review() -> None:
    product_id = uuid4()
    analyzed_pairs: set[tuple[UUID, str]] = set()
    reviews = [
        make_review(product_id=product_id, text_normalized="pos this is great"),
        make_review(product_id=product_id, text_normalized="neg this is terrible"),
    ]
    review_repository = FakeReviewRepository(reviews=reviews, analyzed_pairs=analyzed_pairs)
    sentiment_repository = FakeReviewSentimentRepository(analyzed_pairs=analyzed_pairs)

    summary = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=FakeAnalyzer(),
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )

    assert summary.analyzed == 2
    assert summary.label_counts == {"positive": 1, "negative": 1}
    assert all(review.status == ReviewStatus.READY for review in reviews)
    assert len(sentiment_repository.records) == 2


@pytest.mark.asyncio
async def test_analyze_pending_reviews_is_idempotent_for_the_same_model_version() -> None:
    product_id = uuid4()
    analyzed_pairs: set[tuple[UUID, str]] = set()
    reviews = [make_review(product_id=product_id, text_normalized="pos great app")]
    review_repository = FakeReviewRepository(reviews=reviews, analyzed_pairs=analyzed_pairs)
    sentiment_repository = FakeReviewSentimentRepository(analyzed_pairs=analyzed_pairs)
    analyzer = FakeAnalyzer()

    first = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=analyzer,
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )
    second = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=analyzer,
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )

    assert first.analyzed == 1
    assert second.analyzed == 0


@pytest.mark.asyncio
async def test_analyze_pending_reviews_reanalyzes_under_a_new_model_version() -> None:
    product_id = uuid4()
    analyzed_pairs: set[tuple[UUID, str]] = set()
    reviews = [make_review(product_id=product_id, text_normalized="pos great app")]
    review_repository = FakeReviewRepository(reviews=reviews, analyzed_pairs=analyzed_pairs)
    sentiment_repository = FakeReviewSentimentRepository(analyzed_pairs=analyzed_pairs)
    analyzer = FakeAnalyzer()

    await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=analyzer,
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )
    second = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=analyzer,
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v2",
    )

    assert second.analyzed == 1
    assert len(sentiment_repository.records) == 2


@pytest.mark.asyncio
async def test_analyze_pending_reviews_handles_no_pending_reviews() -> None:
    product_id = uuid4()
    review_repository = FakeReviewRepository(reviews=[])
    sentiment_repository = FakeReviewSentimentRepository()

    summary = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=FakeAnalyzer(),
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )

    assert summary.analyzed == 0
    assert summary.label_counts == {}


@pytest.mark.asyncio
async def test_analyze_pending_reviews_only_targets_the_given_product() -> None:
    product_id = uuid4()
    other_product_id = uuid4()
    reviews = [
        make_review(product_id=product_id, text_normalized="pos in scope"),
        make_review(product_id=other_product_id, text_normalized="pos other product"),
    ]
    review_repository = FakeReviewRepository(reviews=reviews)
    sentiment_repository = FakeReviewSentimentRepository()

    summary = await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=FakeAnalyzer(),
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )

    assert summary.analyzed == 1


@pytest.mark.asyncio
async def test_aggregate_distribution_counts_by_label_for_the_pinned_version() -> None:
    product_id = uuid4()
    sentiment_repository = FakeReviewSentimentRepository()
    reviews = [
        make_review(product_id=product_id, text_normalized="pos a"),
        make_review(product_id=product_id, text_normalized="pos b"),
        make_review(product_id=product_id, text_normalized="neg c"),
    ]
    review_repository = FakeReviewRepository(reviews=reviews)

    await analyze_pending_reviews(
        review_repository=review_repository,
        sentiment_repository=sentiment_repository,
        analyzer=FakeAnalyzer(),
        product_id=product_id,
        model_name="tfidf-logreg",
        model_version="v1",
    )

    distribution = await sentiment_repository.aggregate_distribution(product_id, model_version="v1")
    assert distribution == {SentimentLabel.POSITIVE: 2, SentimentLabel.NEGATIVE: 1}
