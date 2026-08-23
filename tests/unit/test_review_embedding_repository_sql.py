"""Compile-only checks for the review_embeddings upsert and similarity-search SQL.

Same rationale as test_review_sentiment_repository_sql.py: no live PostgreSQL/pgvector
is available in every environment this repo is developed in, so these compile the
actual SQLAlchemy constructs and assert they produce valid-looking SQL.
"""

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert as pg_insert

from voxera.db.models import Review, ReviewEmbedding
from voxera.db.models.review_embedding import EMBEDDING_DIMENSIONS
from voxera.embeddings.model import DEFAULT_DIMENSIONS


def test_embedding_dimensions_constant_matches_the_model_default() -> None:
    # These are two intentionally independent declarations (see the comments on both
    # sides) that must agree for inserts into a fixed-width pgvector column to work.
    assert EMBEDDING_DIMENSIONS == DEFAULT_DIMENSIONS


def test_upsert_statement_compiles_with_on_conflict_update() -> None:
    embedding = [0.1] * EMBEDDING_DIMENSIONS
    statement = (
        pg_insert(ReviewEmbedding)
        .values(
            organization_id=uuid4(),
            product_id=uuid4(),
            review_id=uuid4(),
            model_name="tfidf-svd",
            model_version="v1",
            embedding=embedding,
        )
        .on_conflict_do_update(
            index_elements=["review_id", "model_version"],
            set_={"embedding": embedding},
        )
        .returning(ReviewEmbedding)
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO review_embeddings" in compiled
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE SET" in compiled
    assert "RETURNING" in compiled


def test_search_similar_statement_compiles_with_cosine_distance_ordering() -> None:
    query_embedding = [0.2] * EMBEDDING_DIMENSIONS
    distance = ReviewEmbedding.embedding.cosine_distance(query_embedding)
    similarity = (1 - distance).label("similarity")

    statement = (
        select(Review, similarity)
        .join(ReviewEmbedding, ReviewEmbedding.review_id == Review.id)
        .where(
            ReviewEmbedding.organization_id == uuid4(),
            ReviewEmbedding.product_id == uuid4(),
            ReviewEmbedding.model_version == "v1",
        )
        .order_by(distance)
        .limit(10)
    )

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "SELECT reviews" in compiled
    assert "JOIN review_embeddings" in compiled
    assert "<=>" in compiled  # pgvector cosine-distance operator
    assert "ORDER BY" in compiled
