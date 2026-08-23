import pytest
from tests.unit.fakes import FakeObjectStorage

from voxera.db.models.enums import SentimentLabel
from voxera.ml.sentiment.dataset import SENTIMENT_LABELS, SentimentExample, load_examples
from voxera.ml.sentiment.evaluation import evaluate_model
from voxera.ml.sentiment.model import SentimentBaselineModel
from voxera.ml.sentiment.registry import SentimentModelRegistry
from voxera.ml.sentiment.train import DEFAULT_GOLDEN_PATH, DEFAULT_TRAIN_PATH, train_and_evaluate

TRAIN_EXAMPLES = [
    SentimentExample("Bu uygulama harika, çok memnun kaldım.", "positive"),
    SentimentExample("This app is fantastic, I'm really happy with it.", "positive"),
    SentimentExample("Harika bir deneyimdi, çok başarılı.", "positive"),
    SentimentExample("Great experience, works wonderfully.", "positive"),
    SentimentExample("Uygulama sürekli çöküyor, berbat.", "negative"),
    SentimentExample("The app keeps crashing, absolutely terrible.", "negative"),
    SentimentExample("Giriş yapamıyorum, çok kötü bir deneyim.", "negative"),
    SentimentExample("I can't log in, awful experience.", "negative"),
    SentimentExample("Uygulama geçen hafta güncellendi.", "neutral"),
    SentimentExample("The app was updated last week.", "neutral"),
    SentimentExample("Ayarlar menüsünde dil seçeneği var.", "neutral"),
    SentimentExample("There is a language option in the settings menu.", "neutral"),
]


def test_sentiment_label_enum_matches_ml_label_set() -> None:
    assert set(SENTIMENT_LABELS) == {label.value for label in SentimentLabel}


def test_sentiment_example_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="unknown sentiment label"):
        SentimentExample("text", "mixed")


def test_load_examples_reads_bundled_datasets() -> None:
    train_examples = load_examples(DEFAULT_TRAIN_PATH)
    golden_examples = load_examples(DEFAULT_GOLDEN_PATH)

    assert len(train_examples) > 0
    assert len(golden_examples) > 0
    assert all(example.label in SENTIMENT_LABELS for example in train_examples)
    train_texts = {example.text for example in train_examples}
    golden_texts = {example.text for example in golden_examples}
    assert train_texts.isdisjoint(golden_texts)


def test_model_fit_rejects_empty_dataset() -> None:
    with pytest.raises(ValueError, match="empty dataset"):
        SentimentBaselineModel().fit([])


def test_model_predict_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="not been fitted"):
        SentimentBaselineModel().predict_one("great")


def test_model_predicts_reasonable_labels_after_fitting() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)

    positive = model.predict_one("Gerçekten harika ve başarılı bir uygulama.")
    negative = model.predict_one("Uygulama çöküyor, tamamen berbat.")

    assert positive.label == "positive"
    assert negative.label == "negative"
    assert 0.0 <= positive.score <= 1.0
    assert 0.0 <= negative.score <= 1.0


def test_model_predict_many_returns_one_prediction_per_text() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    predictions = model.predict_many(["Harika!", "Berbat.", "Uygulama güncellendi."])
    assert len(predictions) == 3


def test_model_predict_many_handles_empty_input() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    assert model.predict_many([]) == []


def test_model_roundtrips_through_bytes() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    restored = SentimentBaselineModel.from_bytes(model.to_bytes())

    original = model.predict_one("Harika bir güncelleme oldu.")
    reloaded = restored.predict_one("Harika bir güncelleme oldu.")
    assert original == reloaded


def test_evaluate_model_reports_metrics_for_every_label() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    report = evaluate_model(model, TRAIN_EXAMPLES)

    assert set(report.per_label) == set(SENTIMENT_LABELS)
    assert 0.0 <= report.accuracy <= 1.0
    assert 0.0 <= report.macro_f1 <= 1.0
    assert report.sample_count == len(TRAIN_EXAMPLES)
    assert len(report.confusion_matrix) == len(SENTIMENT_LABELS)


def test_evaluate_model_rejects_empty_dataset() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    with pytest.raises(ValueError, match="empty dataset"):
        evaluate_model(model, [])


def test_train_and_evaluate_returns_a_fitted_model_and_report() -> None:
    model, report = train_and_evaluate(TRAIN_EXAMPLES, TRAIN_EXAMPLES)
    assert model.predict_one("Harika!").label in SENTIMENT_LABELS
    assert report.sample_count == len(TRAIN_EXAMPLES)


def test_registry_saves_and_loads_model_and_report() -> None:
    model = SentimentBaselineModel().fit(TRAIN_EXAMPLES)
    report = evaluate_model(model, TRAIN_EXAMPLES)
    storage = FakeObjectStorage()
    registry = SentimentModelRegistry(storage)

    registry.save("v1", model, report)
    loaded_model = registry.load("v1")
    loaded_report = registry.load_report("v1")

    assert loaded_model.predict_one("Harika!").label == model.predict_one("Harika!").label
    assert loaded_report["sample_count"] == report.sample_count
