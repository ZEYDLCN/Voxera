from voxera.preprocessing.hashing import content_hash
from voxera.preprocessing.html import strip_html
from voxera.preprocessing.language import detect_language
from voxera.preprocessing.normalization import normalize_text
from voxera.preprocessing.pii import mask_pii
from voxera.preprocessing.pipeline import preprocess_review_text


def test_strip_html_removes_tags_and_unescapes_entities() -> None:
    assert strip_html("<b>Great app</b> &amp; fast") == " Great app  & fast"


def test_normalize_text_collapses_whitespace_and_urls() -> None:
    raw = "Check   this out\nhttps://example.com/app  now!!"
    assert normalize_text(raw) == "Check this out now!!"


def test_normalize_text_strips_html() -> None:
    assert normalize_text("<p>Broken   layout</p>") == "Broken layout"


def test_mask_pii_replaces_email_and_phone() -> None:
    text = "Contact me at jane.doe@example.com or +1 415-555-0132 please."
    masked = mask_pii(text)
    assert "[EMAIL]" in masked
    assert "[PHONE]" in masked
    assert "jane.doe@example.com" not in masked
    assert "415-555-0132" not in masked


def test_mask_pii_leaves_ordinary_text_untouched() -> None:
    text = "The app crashes every time I open it."
    assert mask_pii(text) == text


def test_content_hash_is_deterministic_and_sensitive_to_input() -> None:
    assert content_hash("hello") == content_hash("hello")
    assert content_hash("hello") != content_hash("Hello")


def test_detect_language_falls_back_for_short_text() -> None:
    assert detect_language("ok") == "und"
    assert detect_language("  ") == "und"


def test_detect_language_recognizes_turkish_and_english() -> None:
    turkish = "Uygulama son güncellemeden sonra hiç açılmıyor, çok kötü bir deneyim yaşadım."
    english = "The application stopped opening after the last update and support never replied."
    assert detect_language(turkish) == "tr"
    assert detect_language(english) == "en"


def test_preprocess_review_text_produces_clean_and_hashed_output() -> None:
    raw = "  <p>App açılmıyor!! Contact jane@example.com</p>  https://x.co  "
    result = preprocess_review_text(raw)

    assert result.is_meaningful is True
    assert "jane@example.com" not in result.text_redacted
    assert "https://x.co" not in result.text_redacted
    assert result.text_normalized == result.text_redacted.casefold()
    assert result.content_hash == content_hash(result.text_normalized)


def test_preprocess_review_text_uses_declared_language_without_detection() -> None:
    result = preprocess_review_text("ok", declared_language="fr")
    assert result.language == "fr"


def test_preprocess_review_text_flags_empty_text_as_not_meaningful() -> None:
    result = preprocess_review_text("   <p></p>   ")
    assert result.is_meaningful is False
