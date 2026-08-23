import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from voxera.core.config import get_settings
from voxera.db import Database
from voxera.db.repositories.sqlalchemy import SqlAlchemyReviewRepository
from voxera.embeddings.corpus import load_corpus
from voxera.embeddings.model import DEFAULT_DIMENSIONS, TfidfSvdEmbeddingModel
from voxera.embeddings.registry import EmbeddingModelRegistry
from voxera.storage.object_storage import S3ObjectStorage

# src/voxera/embeddings/train.py -> repo root is three parents up.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORPUS_PATH = _REPO_ROOT / "data" / "sentiment" / "train.csv"


def fit_embedding_model(
    texts: list[str],
    *,
    dimensions: int = DEFAULT_DIMENSIONS,
) -> TfidfSvdEmbeddingModel:
    return TfidfSvdEmbeddingModel(dimensions=dimensions).fit(texts)


async def load_corpus_from_database(
    organization_id: UUID,
    product_id: UUID,
    *,
    limit: int,
) -> list[str]:
    """Fit on a tenant's own reviews (the realistic path) rather than the bootstrap
    CSV: an LSA model is only as good as the corpus it was fitted on."""

    settings = get_settings()
    database = Database(settings)
    try:
        async with database.session(organization_id=organization_id) as session:
            reviews = await SqlAlchemyReviewRepository(session, organization_id).list_for_product(
                product_id, limit=limit
            )
            return [review.text_normalized for review in reviews]
    finally:
        await database.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fit the TF-IDF + SVD embedding baseline and publish it to object storage."
    )
    parser.add_argument(
        "--corpus-path",
        default=str(DEFAULT_CORPUS_PATH),
        help="CSV with a 'text' column (ignored if --organization-id is given)",
    )
    parser.add_argument(
        "--organization-id",
        help="fetch the fitting corpus from this org's reviews instead of --corpus-path",
    )
    parser.add_argument("--product-id", help="required together with --organization-id")
    parser.add_argument("--corpus-limit", type=int, default=20000)
    parser.add_argument("--dimensions", type=int, default=DEFAULT_DIMENSIONS)
    parser.add_argument(
        "--version", required=True, help="artifact version, e.g. tfidf-svd-2026-08-23"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fit and print metadata without publishing to object storage",
    )
    args = parser.parse_args()

    if args.organization_id:
        if not args.product_id:
            parser.error("--product-id is required together with --organization-id")
        texts = asyncio.run(
            load_corpus_from_database(
                UUID(args.organization_id),
                UUID(args.product_id),
                limit=args.corpus_limit,
            )
        )
    else:
        texts = load_corpus(args.corpus_path)

    model = fit_embedding_model(texts, dimensions=args.dimensions)
    metadata = {
        "corpus_size": len(texts),
        "requested_dimensions": args.dimensions,
        "effective_dimensions": model.effective_dimensions,
    }
    print(json.dumps(metadata, indent=2))

    if args.dry_run:
        return

    registry = EmbeddingModelRegistry(S3ObjectStorage(get_settings()))
    registry.save(args.version, model, metadata)
    print(f"published embedding model version {args.version!r} to object storage")


if __name__ == "__main__":
    main()
