from dataclasses import dataclass

from sklearn.metrics import classification_report, confusion_matrix

from voxera.ml.sentiment.dataset import SENTIMENT_LABELS, SentimentExample
from voxera.ml.sentiment.model import SentimentBaselineModel


@dataclass(frozen=True, slots=True)
class LabelMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """Classification report for one model version against one dataset.

    Matches the "Classification" evaluation criteria in the project spec: precision,
    recall, F1 and a confusion matrix, per label and macro-averaged.
    """

    accuracy: float
    macro_f1: float
    per_label: dict[str, LabelMetrics]
    confusion_matrix: list[list[int]]
    labels: tuple[str, ...]
    sample_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "accuracy": self.accuracy,
            "macro_f1": self.macro_f1,
            "sample_count": self.sample_count,
            "labels": list(self.labels),
            "per_label": {
                label: {
                    "precision": metrics.precision,
                    "recall": metrics.recall,
                    "f1": metrics.f1,
                    "support": metrics.support,
                }
                for label, metrics in self.per_label.items()
            },
            "confusion_matrix": self.confusion_matrix,
        }


def evaluate_model(
    model: SentimentBaselineModel,
    examples: list[SentimentExample],
) -> EvaluationReport:
    if not examples:
        raise ValueError("cannot evaluate on an empty dataset")

    texts = [example.text for example in examples]
    true_labels = [example.label for example in examples]
    predicted_labels = [prediction.label for prediction in model.predict_many(texts)]

    report = classification_report(
        true_labels,
        predicted_labels,
        labels=list(SENTIMENT_LABELS),
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(true_labels, predicted_labels, labels=list(SENTIMENT_LABELS))

    per_label = {
        label: LabelMetrics(
            precision=report[label]["precision"],
            recall=report[label]["recall"],
            f1=report[label]["f1-score"],
            support=int(report[label]["support"]),
        )
        for label in SENTIMENT_LABELS
    }

    return EvaluationReport(
        accuracy=report["accuracy"],
        macro_f1=report["macro avg"]["f1-score"],
        per_label=per_label,
        confusion_matrix=matrix.tolist(),
        labels=SENTIMENT_LABELS,
        sample_count=len(examples),
    )
