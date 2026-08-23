import io

import joblib
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

# Must match voxera.db.models.review_embedding.EMBEDDING_DIMENSIONS -- pgvector
# columns are fixed-width, so this and the DB schema have to agree.
DEFAULT_DIMENSIONS = 256


class TfidfSvdEmbeddingModel:
    """TF-IDF + Truncated SVD (LSA) embedding baseline.

    The classical-ML rung of the spec's embedding ladder (LSA -> a multilingual
    sentence-transformer such as multilingual-e5, per docs/ROADMAP.md). LSA captures
    term co-occurrence similarity across the fitted corpus -- e.g. "giriş yapamıyorum"
    and "login ekranında hata alıyorum" share almost no vocabulary but do share
    co-occurring context in a large enough review corpus -- without a GPU or a
    multi-gigabyte transformer download. `embed_many` is the contract a
    transformer-based model would implement identically, so
    `voxera.services.embedding_service` and semantic search never have to change when
    the model behind them does.

    Vectors are always returned at exactly `dimensions` length (zero-padded if the
    fitted corpus was too small to support the full width) because pgvector columns
    are fixed-width: `review_embeddings.embedding` is declared `vector(dimensions)`,
    and a mismatched length would fail on insert. Zero-padding a unit-normalized
    vector does not change its norm or its cosine similarity to another vector padded
    the same way, so this is safe.
    """

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS) -> None:
        self.dimensions = dimensions
        self._effective_dimensions = dimensions
        self._vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        self._svd: TruncatedSVD | None = None
        self._fitted = False

    @property
    def effective_dimensions(self) -> int:
        """The SVD's actual output width, before zero-padding to `dimensions`."""

        return self._effective_dimensions

    def fit(self, texts: list[str]) -> "TfidfSvdEmbeddingModel":
        if not texts:
            raise ValueError("cannot fit on an empty corpus")

        tfidf_matrix = self._vectorizer.fit_transform(texts)
        vocabulary_size = tfidf_matrix.shape[1]
        # TruncatedSVD requires n_components < min(n_samples, n_features); clamp for
        # small corpora (chiefly tests/dev) rather than raising -- real review corpora
        # are large enough that this never actually reduces the requested width.
        self._effective_dimensions = max(
            1, min(self.dimensions, vocabulary_size - 1, len(texts) - 1)
        )
        self._svd = TruncatedSVD(n_components=self._effective_dimensions, random_state=13)
        self._svd.fit(tfidf_matrix)
        self._fitted = True
        return self

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self._require_fitted()
        if not texts:
            return []

        assert self._svd is not None
        tfidf_matrix = self._vectorizer.transform(texts)
        reduced = self._svd.transform(tfidf_matrix)
        normalized = normalize(reduced)

        if self._effective_dimensions < self.dimensions:
            pad_width = self.dimensions - self._effective_dimensions
            normalized = np.pad(normalized, ((0, 0), (0, pad_width)))

        result: list[list[float]] = normalized.tolist()
        return result

    def embed_one(self, text: str) -> list[float]:
        return self.embed_many([text])[0]

    def to_bytes(self) -> bytes:
        self._require_fitted()
        buffer = io.BytesIO()
        joblib.dump(
            {
                "vectorizer": self._vectorizer,
                "svd": self._svd,
                "dimensions": self.dimensions,
                "effective_dimensions": self._effective_dimensions,
            },
            buffer,
        )
        return buffer.getvalue()

    @classmethod
    def from_bytes(cls, data: bytes) -> "TfidfSvdEmbeddingModel":
        payload = joblib.load(io.BytesIO(data))
        model = cls(dimensions=payload["dimensions"])
        model._vectorizer = payload["vectorizer"]
        model._svd = payload["svd"]
        model._effective_dimensions = payload["effective_dimensions"]
        model._fitted = True
        return model

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError("model has not been fitted or loaded yet")
