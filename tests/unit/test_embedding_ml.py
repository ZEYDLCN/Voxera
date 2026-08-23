import math

import pytest
from tests.unit.fakes import FakeObjectStorage

from voxera.embeddings.corpus import load_corpus
from voxera.embeddings.model import TfidfSvdEmbeddingModel
from voxera.embeddings.registry import EmbeddingModelRegistry
from voxera.embeddings.train import DEFAULT_CORPUS_PATH, fit_embedding_model

CORPUS = [
    "Uygulamaya giriş yapamıyorum sürekli hata alıyorum",
    "Login ekranında hata alıyorum bir türlü giremiyorum",
    "Hesabıma giremiyorum sürekli hata veriyor",
    "Ödeme ekranında kart bilgilerimi giremiyorum",
    "Yeni tasarım çok güzel olmuş gerçekten beğendim",
    "Arayüz artık çok sade ve kullanışlı görünüyor",
    "Kargo çok hızlı geldi gerçekten memnun kaldım",
    "Teslimat süresi harikaydı çok memnun oldum",
]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def test_model_fit_rejects_empty_corpus() -> None:
    with pytest.raises(ValueError, match="empty corpus"):
        TfidfSvdEmbeddingModel().fit([])


def test_model_embed_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="not been fitted"):
        TfidfSvdEmbeddingModel().embed_one("text")


def test_model_embed_many_handles_empty_input() -> None:
    model = TfidfSvdEmbeddingModel(dimensions=4).fit(CORPUS)
    assert model.embed_many([]) == []


def test_embeddings_are_unit_normalized() -> None:
    model = TfidfSvdEmbeddingModel(dimensions=4).fit(CORPUS)
    vector = model.embed_one(CORPUS[0])
    norm = math.sqrt(sum(x * x for x in vector))
    assert norm == pytest.approx(1.0, abs=1e-6)


def test_embeddings_are_always_the_requested_width() -> None:
    # 8 short documents force TruncatedSVD to clamp well below the requested width,
    # exercising the zero-padding path.
    model = TfidfSvdEmbeddingModel(dimensions=50).fit(CORPUS)
    assert model.effective_dimensions < 50
    vector = model.embed_one(CORPUS[0])
    assert len(vector) == 50


def test_similar_reviews_score_higher_than_unrelated_ones() -> None:
    model = TfidfSvdEmbeddingModel(dimensions=6).fit(CORPUS)

    query = model.embed_one("Giriş yapamıyorum hesabıma giremiyorum sürekli hata")
    login_review = model.embed_one(CORPUS[1])  # also about login
    delivery_review = model.embed_one(CORPUS[6])  # about delivery, unrelated

    assert _cosine(query, login_review) > _cosine(query, delivery_review)


def test_model_roundtrips_through_bytes() -> None:
    model = TfidfSvdEmbeddingModel(dimensions=6).fit(CORPUS)
    restored = TfidfSvdEmbeddingModel.from_bytes(model.to_bytes())

    assert restored.embed_one(CORPUS[0]) == model.embed_one(CORPUS[0])
    assert restored.dimensions == model.dimensions
    assert restored.effective_dimensions == model.effective_dimensions


def test_registry_saves_and_loads_model_and_metadata() -> None:
    model = TfidfSvdEmbeddingModel(dimensions=6).fit(CORPUS)
    storage = FakeObjectStorage()
    registry = EmbeddingModelRegistry(storage)

    registry.save("v1", model, {"corpus_size": len(CORPUS)})
    loaded_model = registry.load("v1")
    loaded_metadata = registry.load_metadata("v1")

    assert loaded_model.embed_one(CORPUS[0]) == model.embed_one(CORPUS[0])
    assert loaded_metadata["corpus_size"] == len(CORPUS)


def test_load_corpus_reads_the_bundled_bootstrap_dataset() -> None:
    texts = load_corpus(DEFAULT_CORPUS_PATH)
    assert len(texts) > 0
    assert all(isinstance(text, str) and text for text in texts)


def test_fit_embedding_model_matches_direct_construction() -> None:
    model = fit_embedding_model(CORPUS, dimensions=6)
    assert model.embed_one(CORPUS[0]) == TfidfSvdEmbeddingModel(dimensions=6).fit(CORPUS).embed_one(
        CORPUS[0]
    )
