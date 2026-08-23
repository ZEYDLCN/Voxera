import csv
from pathlib import Path


def load_corpus(path: str | Path) -> list[str]:
    """Load review text from any CSV with a `text` column (other columns are ignored).

    Compatible with `data/sentiment/train.csv`, so the same bilingual bootstrap
    reviews can seed both the sentiment baseline and the embedding baseline without
    a separate dataset file -- see data/sentiment/README.md.
    """

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["text"] for row in reader]
