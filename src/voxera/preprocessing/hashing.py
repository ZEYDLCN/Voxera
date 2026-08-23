import hashlib


def content_hash(text: str) -> str:
    """Return a stable SHA-256 hex digest used for exact-duplicate review detection."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
