import io
from dataclasses import dataclass

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from voxera.ml.sentiment.dataset import SentimentExample


@dataclass(frozen=True, slots=True)
class SentimentPrediction:
    label: str
    score: float
    """Confidence of the predicted label, in [0, 1]."""


class SentimentBaselineModel:
    """TF-IDF + Logistic Regression sentiment classifier.

    Deliberately the simplest rung of the model-comparison ladder described in the
    project spec (baseline -> transformer -> domain fine-tune). `predict_many` is the
    contract a transformer-based model would implement identically, so
    `voxera.services.sentiment_analysis_service` never has to change when the model
    behind it does.
    """

    def __init__(self, pipeline: Pipeline | None = None) -> None:
        self._pipeline = pipeline or Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
                ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
            ]
        )
        self._fitted = pipeline is not None

    def fit(self, examples: list[SentimentExample]) -> "SentimentBaselineModel":
        if not examples:
            raise ValueError("cannot fit on an empty dataset")
        texts = [example.text for example in examples]
        labels = [example.label for example in examples]
        self._pipeline.fit(texts, labels)
        self._fitted = True
        return self

    def predict_many(self, texts: list[str]) -> list[SentimentPrediction]:
        self._require_fitted()
        if not texts:
            return []

        probabilities = self._pipeline.predict_proba(texts)
        classes = self._pipeline.named_steps["clf"].classes_
        predictions = []
        for row in probabilities:
            best_index = row.argmax()
            predictions.append(
                SentimentPrediction(label=str(classes[best_index]), score=float(row[best_index]))
            )
        return predictions

    def predict_one(self, text: str) -> SentimentPrediction:
        return self.predict_many([text])[0]

    def to_bytes(self) -> bytes:
        """Serialize the fitted pipeline so it composes with `ObjectStorage.put_bytes`."""

        self._require_fitted()
        buffer = io.BytesIO()
        joblib.dump(self._pipeline, buffer)
        return buffer.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "SentimentBaselineModel":
        pipeline = joblib.load(io.BytesIO(data))
        return cls(pipeline=pipeline)

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("model has not been fitted or loaded yet")
