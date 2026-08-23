import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawReviewRow(BaseModel):
    """Unified Review Object: the common shape every source is normalized into.

    Raw Review -> Normalizer -> Unified Review Object. CSV columns and JSON fields are
    both validated against this single schema so downstream preprocessing never has to
    know where a row came from.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str
    occurred_at: datetime
    external_id: str | None = None
    rating: int | None = None
    language: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("external_id", "language", "rating", mode="before")
    @classmethod
    def blank_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("attributes", mode="before")
    @classmethod
    def parse_json_string_attributes(cls, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value) if value.strip() else {}
        return value

    @field_validator("text")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("rating")
    @classmethod
    def rating_within_bounds(cls, value: int | None) -> int | None:
        if value is not None and not (1 <= value <= 5):
            raise ValueError("rating must be between 1 and 5")
        return value
