import csv
import json
from collections.abc import Iterator
from typing import TextIO

from pydantic import ValidationError

from voxera.ingestion.errors import RowError
from voxera.ingestion.schemas import RawReviewRow

ParsedRow = tuple[int, RawReviewRow | None, RowError | None]


def parse_csv(stream: TextIO) -> Iterator[ParsedRow]:
    """Stream a CSV file row by row so a single bad row never aborts the whole import."""

    reader = csv.DictReader(stream)
    for row_number, raw_row in enumerate(reader, start=2):  # header occupies row 1
        row, reason = _validate(raw_row)
        yield row_number, row, RowError(row_number, reason) if reason else None


def parse_json_lines(stream: TextIO) -> Iterator[ParsedRow]:
    """Stream newline-delimited JSON (one review object per line)."""

    for row_number, line in enumerate(stream, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            yield row_number, None, RowError(row_number, f"invalid json: {exc.msg}")
            continue
        row, reason = _validate(payload)
        yield row_number, row, RowError(row_number, reason) if reason else None


def parse_json_array(stream: TextIO) -> Iterator[ParsedRow]:
    """Parse a single JSON array of review objects.

    Unlike the streaming parsers this must buffer the whole payload in memory, so very
    large imports should prefer the JSON Lines format.
    """

    try:
        payload = json.load(stream)
    except json.JSONDecodeError as exc:
        yield 1, None, RowError(1, f"invalid json: {exc.msg}")
        return
    if not isinstance(payload, list):
        yield 1, None, RowError(1, "json payload must be an array of review objects")
        return
    for row_number, item in enumerate(payload, start=1):
        row, reason = _validate(item)
        yield row_number, row, RowError(row_number, reason) if reason else None


def _validate(raw_row: object) -> tuple[RawReviewRow | None, str | None]:
    try:
        return RawReviewRow.model_validate(raw_row), None
    except ValidationError as exc:
        return None, _format_validation_error(exc)


def _format_validation_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(part) for part in first["loc"]) or "value"
    return f"{location}: {first['msg']}"
