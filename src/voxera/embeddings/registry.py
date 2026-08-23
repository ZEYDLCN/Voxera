import json
from typing import Any

from voxera.embeddings.model import TfidfSvdEmbeddingModel
from voxera.storage.object_storage import ObjectStorage

_PREFIX = "models/embeddings"


class EmbeddingModelRegistry:
    """Versioned embedding model storage on top of `ObjectStorage`.

    Same key convention and division of responsibility as
    `voxera.ml.sentiment.registry.SentimentModelRegistry` -- see that module for the
    rationale. Kept as a separate, independent class rather than a shared generic base:
    the two artifacts (a classifier vs. a vectorizer+SVD pair) and their metadata
    shapes are different enough that sharing would add more indirection than it saves.
    """

    def __init__(self, object_storage: ObjectStorage) -> None:
        self._storage = object_storage

    def save(
        self,
        version: str,
        model: TfidfSvdEmbeddingModel,
        metadata: dict[str, Any],
    ) -> None:
        self._storage.put_bytes(
            self._model_key(version),
            model.to_bytes(),
            content_type="application/octet-stream",
        )
        self._storage.put_bytes(
            self._metadata_key(version),
            json.dumps(metadata, indent=2).encode("utf-8"),
            content_type="application/json",
        )

    def load(self, version: str) -> TfidfSvdEmbeddingModel:
        return TfidfSvdEmbeddingModel.from_bytes(self._storage.get_bytes(self._model_key(version)))

    def load_metadata(self, version: str) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self._storage.get_bytes(self._metadata_key(version)))
        return payload

    def _model_key(self, version: str) -> str:
        return f"{_PREFIX}/{version}/model.joblib"

    def _metadata_key(self, version: str) -> str:
        return f"{_PREFIX}/{version}/metadata.json"
