"""Golden-dataset regression test for the sentiment baseline.

Trains on data/sentiment/train.csv and asserts the macro F1 on the held-out
data/sentiment/golden.csv does not regress below a fixed floor. Re-run this whenever
the model, its hyperparameters, or the training data change (see docs/ROADMAP.md
Phase 4 and the project spec's "Golden Dataset" section) -- a drop below the floor
means something got worse, not necessarily that the floor should move.
"""

from voxera.ml.sentiment.dataset import load_examples
from voxera.ml.sentiment.train import DEFAULT_GOLDEN_PATH, DEFAULT_TRAIN_PATH, train_and_evaluate

# Currently trained/evaluated macro F1 is ~0.84 on the bundled bootstrap dataset (see
# data/sentiment/README.md); the floor leaves headroom for the small dataset's
# variance while still catching a real regression.
MINIMUM_MACRO_F1 = 0.6


def test_sentiment_baseline_meets_golden_f1_floor() -> None:
    train_examples = load_examples(DEFAULT_TRAIN_PATH)
    golden_examples = load_examples(DEFAULT_GOLDEN_PATH)

    _, report = train_and_evaluate(train_examples, golden_examples)

    assert report.macro_f1 >= MINIMUM_MACRO_F1, (
        f"sentiment baseline macro F1 regressed to {report.macro_f1:.3f} "
        f"(floor is {MINIMUM_MACRO_F1})"
    )
