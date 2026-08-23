from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RowError:
    """A single row that failed schema validation during ingestion."""

    row_number: int
    reason: str
