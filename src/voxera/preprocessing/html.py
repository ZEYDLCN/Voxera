import re

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_RE = re.compile(r"&(amp|lt|gt|quot|#39|apos);")

_ENTITY_REPLACEMENTS = {
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "#39": "'",
    "apos": "'",
}


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape the small set of common named entities."""

    without_tags = _TAG_RE.sub(" ", text)
    return _ENTITY_RE.sub(lambda match: _ENTITY_REPLACEMENTS[match.group(1)], without_tags)
