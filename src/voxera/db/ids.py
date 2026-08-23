import secrets
import time
from uuid import UUID

_MAX_UNIX_MILLISECONDS = (1 << 48) - 1


def uuid7() -> UUID:
    """Return an RFC 9562 UUIDv7 with millisecond-sortable timestamp bits."""

    unix_milliseconds = time.time_ns() // 1_000_000
    if unix_milliseconds > _MAX_UNIX_MILLISECONDS:
        raise OverflowError("current timestamp cannot be represented as UUIDv7")

    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (
        (unix_milliseconds << 80)
        | (0b0111 << 76)
        | (random_a << 64)
        | (0b10 << 62)
        | random_b
    )
    return UUID(int=value)


def uuid7_timestamp_milliseconds(value: UUID) -> int:
    """Extract the Unix millisecond timestamp from a UUIDv7 value."""

    if value.version != 7:
        raise ValueError("value is not a UUIDv7")
    return value.int >> 80

