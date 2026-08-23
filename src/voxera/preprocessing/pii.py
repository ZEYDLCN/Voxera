import re

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d\s().-]{7,}\d)(?!\w)")


def mask_pii(text: str) -> str:
    """Replace obvious email/phone PII with stable placeholders.

    This is a conservative MVP heuristic, not a full PII-detection model. It masks common
    review-text patterns (support emails, phone numbers left by frustrated users) so raw
    contact details never reach embeddings, LLM prompts or dashboards.
    """

    masked = _EMAIL_RE.sub("[EMAIL]", text)
    return _PHONE_RE.sub("[PHONE]", masked)
