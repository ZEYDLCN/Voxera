import argparse
import json
from pathlib import Path

from voxera.core.config import get_settings
from voxera.ml.sentiment.dataset import SentimentExample, load_examples
from voxera.ml.sentiment.evaluation import EvaluationReport, evaluate_model
from voxera.ml.sentiment.model import SentimentBaselineModel
from voxera.ml.sentiment.registry import SentimentModelRegistry
from voxera.storage.object_storage import S3ObjectStorage

# src/voxera/ml/sentiment/train.py -> repo root is four parents up.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_TRAIN_PATH = _REPO_ROOT / "data" / "sentiment" / "train.csv"
DEFAULT_GOLDEN_PATH = _REPO_ROOT / "data" / "sentiment" / "golden.csv"


def train_and_evaluate(
    train_examples: list[SentimentExample],
    golden_examples: list[SentimentExample],
) -> tuple[SentimentBaselineModel, EvaluationReport]:
    """Fit on `train_examples`, report metrics on the held-out `golden_examples`."""

    model = SentimentBaselineModel().fit(train_examples)
    report = evaluate_model(model, golden_examples)
    return model, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train the TF-IDF + Logistic Regression sentiment baseline, "
        "evaluate it against the golden set, and publish it to object storage."
    )
    parser.add_argument("--train-path", default=str(DEFAULT_TRAIN_PATH))
    parser.add_argument("--golden-path", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument(
        "--version", required=True, help="artifact version, e.g. tfidf-logreg-2026-08-23"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="train and print the evaluation report without publishing to object storage",
    )
    args = parser.parse_args()

    train_examples = load_examples(args.train_path)
    golden_examples = load_examples(args.golden_path)
    model, report = train_and_evaluate(train_examples, golden_examples)

    print(json.dumps(report.to_dict(), indent=2))

    if args.dry_run:
        return

    registry = SentimentModelRegistry(S3ObjectStorage(get_settings()))
    registry.save(args.version, model, report)
    print(f"published sentiment model version {args.version!r} to object storage")


if __name__ == "__main__":
    main()
