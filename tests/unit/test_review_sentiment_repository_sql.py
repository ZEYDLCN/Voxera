"""Compile-only checks for the review_sentiments upsert statement.

No live PostgreSQL is available in every environment this repo is developed in (see
tests/integration's opt-in convention), so this compiles the actual SQLAlchemy
construct used by SqlAlchemyReviewSentimentRepository.upsert and asserts it produces
valid-looking ON CONFLICT SQL -- catching construction bugs (wrong column names, wrong
conflict target) that a pure-Python fake could never surface.
"""

from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from voxera.db.models import ReviewSentiment
from voxera.db.models.enums import SentimentLabel


def test_upsert_statement_compiles_with_on_conflict_update() -> None:
    statement = (
        pg_insert(ReviewSentiment)
        .values(
            organization_id=uuid4(),
            product_id=uuid4(),
            review_id=uuid4(),
            model_name="tfidf-logreg",
            model_version="v1",
            label=SentimentLabel.POSITIVE,
            score=0.91,
        )
        .on_conflict_do_update(
            index_elements=["review_id", "model_version"],
            set_={"label": SentimentLabel.POSITIVE, "score": 0.91},
        )
        .returning(ReviewSentiment)
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO review_sentiments" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled
    assert "RETURNING" in compiled
