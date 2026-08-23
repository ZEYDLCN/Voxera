from dataclasses import dataclass

from voxera.preprocessing.hashing import content_hash
from voxera.preprocessing.language import detect_language
from voxera.preprocessing.normalization import normalize_text
from voxera.preprocessing.pii import mask_pii

MIN_MEANINGFUL_LENGTH = 3


@dataclass(frozen=True, slots=True)
class PreprocessedText:
    """Result of running raw review text through the Voxera cleaning pipeline."""

    text_redacted: str
    """Cleaned, PII-masked text kept in its original casing for display."""

    text_normalized: str
    """Case-folded form used for hashing, deduplication and downstream ML."""

    language: str
    content_hash: str
    is_meaningful: bool
    """False when the review is too short/empty to analyze after cleaning."""


def preprocess_review_text(
    raw_text: str,
    *,
    declared_language: str | None = None,
) -> PreprocessedText:
    """Raw Text -> Language Detection -> Normalization -> Noise Removal -> Clean Text.

    `declared_language` lets a source's own metadata (e.g. an app store locale) skip
    detection when it is already known and trusted.
    """

    normalized = normalize_text(raw_text)
    redacted = mask_pii(normalized)
    folded = redacted.casefold()
    language = declared_language or detect_language(redacted)

    return PreprocessedText(
        text_redacted=redacted,
        text_normalized=folded,
        language=language,
        content_hash=content_hash(folded),
        is_meaningful=len(redacted) >= MIN_MEANINGFUL_LENGTH,
    )
