import re
import unicodedata

from voxera.preprocessing.html import strip_html

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def strip_urls(text: str) -> str:
    return _URL_RE.sub(" ", text)


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """Apply the MVP cleaning pipeline: unicode normalize, de-HTML, de-URL, collapse space.

    Aggressive stemming/stopword removal is intentionally skipped -- modern embedding and
    transformer models do not need it and it destroys information sentiment models rely on.
    """

    normalized = unicodedata.normalize("NFKC", text)
    normalized = strip_html(normalized)
    normalized = strip_urls(normalized)
    return collapse_whitespace(normalized)
