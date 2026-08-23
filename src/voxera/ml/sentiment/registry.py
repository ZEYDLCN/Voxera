import json
from typing import Any

from voxera.ml.sentiment.evaluation import EvaluationReport
from voxera.ml.sentiment.model import SentimentBaselineModel
from voxera.storage.object_storage import ObjectStorage

_PREFIX = "models/sentiment"


class SentimentModelRegistry:
    """Versioned sentiment model storage on top of `ObjectStorage`.

    Key convention: `models/sentiment/{version}/model.joblib` and
    `models/sentiment/{version}/evaluation.json`. Any ObjectStorage-compatible backend
    (S3, MinIO, or a fake in tests) works without this module knowing which one it is
    -- the same Protocol used for raw import files backs model artifacts too.
    """

    def __init__(self, object_storage: ObjectStorage) -> None:
        self._storage = object_storage

    def save(
        self,
        version: str,
        model: SentimentBaselineModel,
        report: EvaluationReport,
    ) -> None:
        self._storage.put_bytes(
            self._model_key(version),
            model.to_bytes(),
            content_type="application/octet-stream",
        )
        self._storage.put_bytes(
            self._report_key(version),
            json.dumps(report.to_dict(), indent=2).encode("utf-8"),
            content_type="application/json",
        )

    def load(self, version: str) -> SentimentBaselineModel:
        return SentimentBaselineModel.from_bytes(self._storage.get_bytes(self._model_key(version)))

    def load_report(self, version: str) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self._storage.get_bytes(self._report_key(version)))
        return payload

    def _model_key(self, version: str) -> str:
        return f"{_PREFIX}/{version}/model.joblib"

    def _report_key(self, version: str) -> str:
        return f"{_PREFIX}/{version}/evaluation.json"
