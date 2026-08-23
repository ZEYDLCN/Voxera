from datetime import UTC, datetime
from uuid import uuid4

import pytest

from voxera.db.ids import uuid7, uuid7_timestamp_milliseconds


def test_uuid7_contains_current_timestamp_and_rfc_bits() -> None:
    before = int(datetime.now(UTC).timestamp() * 1000)
    value = uuid7()
    after = int(datetime.now(UTC).timestamp() * 1000)

    assert value.version == 7
    assert value.variant == "specified in RFC 4122"
    assert before <= uuid7_timestamp_milliseconds(value) <= after


def test_uuid7_timestamp_rejects_other_versions() -> None:
    with pytest.raises(ValueError, match="not a UUIDv7"):
        uuid7_timestamp_milliseconds(uuid4())


def test_uuid7_values_are_unique() -> None:
    values = {uuid7() for _ in range(1_000)}

    assert len(values) == 1_000

