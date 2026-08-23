from langdetect import DetectorFactory, LangDetectException, detect

# langdetect's Naive Bayes sampling is non-deterministic by default; pin the seed so the
# same text always resolves to the same language across requests and test runs.
DetectorFactory.seed = 0

UNKNOWN_LANGUAGE = "und"
_MIN_DETECTABLE_LENGTH = 3


def detect_language(text: str, *, default: str = UNKNOWN_LANGUAGE) -> str:
    """Best-effort ISO 639-1 language detection with a safe fallback.

    Short or ambiguous text is common in review data ("ok", "5 stars") and is not worth
    misclassifying, so anything below the minimum length short-circuits to `default`.
    """

    stripped = text.strip()
    if len(stripped) < _MIN_DETECTABLE_LENGTH:
        return default
    try:
        return str(detect(stripped))
    except LangDetectException:
        return default
