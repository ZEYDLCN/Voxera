from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from voxera.db.models.enums import SentimentLabel
from voxera.db.repositories.contracts import (
    ReviewRepository,
    ReviewSentimentCreate,
    ReviewSentimentRepository,
)
from voxera.ml.sentiment.model import SentimentPrediction

DEFAULT_ANALYSIS_BATCH_LIMIT = 500


class SentimentAnalyzer(Protocol):
    """Anything that scores review text for sentiment.

    `SentimentBaselineModel` implements this today; a transformer-based model -- the
    next rung of the spec's model-comparison ladder -- can be swapped in later without
    this service (or the API route calling it) changing at all.
    """

    def predict_many(self, texts: list[str]) -> list[SentimentPrediction]: ...


@dataclass(slots=True)
class SentimentAnalysisSummary:
    analyzed: int = 0
    label_counts: dict[str, int] = field(default_factory=dict)


async def analyze_pending_reviews(
    *,
    review_repository: ReviewRepository,
    sentiment_repository: ReviewSentimentRepository,
    analyzer: SentimentAnalyzer,
    product_id: UUID,
    model_name: str,
    model_version: str,
    limit: int = DEFAULT_ANALYSIS_BATCH_LIMIT,
) -> SentimentAnalysisSummary:
    """Score every review for `product_id` with no result yet for `model_version`.

    Idempotent and safely re-runnable: `ReviewRepository.list_for_analysis` already
    excludes reviews that have a result for this exact model version, so calling this
    repeatedly (e.g. after every import, or on a schedule) only ever processes
    genuinely new reviews -- no separate "have I run this version yet" bookkeeping.
    """

    reviews = await review_repository.list_for_analysis(
        product_id,
        model_version=model_version,
        limit=limit,
    )
    if not reviews:
        return SentimentAnalysisSummary()

    predictions = analyzer.predict_many([review.text_normalized for review in reviews])

    summary = SentimentAnalysisSummary()
    for review, prediction in zip(reviews, predictions, strict=True):
        await sentiment_repository.upsert(
            ReviewSentimentCreate(
                product_id=product_id,
                review_id=review.id,
                model_name=model_name,
                model_version=model_version,
                label=SentimentLabel(prediction.label),
                score=prediction.score,
            )
        )
        await review_repository.mark_ready(review.id)
        summary.analyzed += 1
        summary.label_counts[prediction.label] = summary.label_counts.get(prediction.label, 0) + 1

    return summary
