import csv
from dataclasses import dataclass
from pathlib import Path

SENTIMENT_LABELS = ("negative", "neutral", "positive")


@dataclass(frozen=True, slots=True)
class SentimentExample:
    text: str
    label: str

    def __post_init__(self) -> None:
        if self.label not in SENTIMENT_LABELS:
            raise ValueError(f"unknown sentiment label {self.label!r}")


def load_examples(path: str | Path) -> list[SentimentExample]:
    """Load a `text,label` CSV (see data/sentiment/README.md) into examples."""

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [SentimentExample(text=row["text"], label=row["label"]) for row in reader]
