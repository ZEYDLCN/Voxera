import io

from voxera.ingestion.parsers import parse_csv, parse_json_array, parse_json_lines


def test_parse_csv_validates_and_reports_row_numbers() -> None:
    csv_text = (
        "text,rating,occurred_at,external_id\n"
        "Great app,5,2026-08-12T14:23:00,ext-1\n"
        ",3,2026-08-12T14:24:00,ext-2\n"
        "Broken login,9,2026-08-12T14:25:00,ext-3\n"
    )
    rows = list(parse_csv(io.StringIO(csv_text)))

    assert [row_number for row_number, _, _ in rows] == [2, 3, 4]

    row, parsed, error = rows[0]
    assert parsed is not None and error is None
    assert parsed.text == "Great app"
    assert parsed.rating == 5
    assert parsed.external_id == "ext-1"

    _, parsed, error = rows[1]
    assert parsed is None and error is not None
    assert error.row_number == 3

    _, parsed, error = rows[2]
    assert parsed is None and error is not None
    assert "rating" in error.reason


def test_parse_csv_treats_blank_optional_fields_as_none() -> None:
    csv_text = "text,rating,occurred_at,external_id\nFine,,2026-08-12T14:23:00,\n"
    _, parsed, error = next(iter(parse_csv(io.StringIO(csv_text))))
    assert error is None
    assert parsed is not None
    assert parsed.rating is None
    assert parsed.external_id is None


def test_parse_json_lines_streams_one_object_per_line() -> None:
    payload = (
        '{"text": "Nice", "occurred_at": "2026-08-12T14:23:00"}\n'
        "not json\n"
        '{"text": "", "occurred_at": "2026-08-12T14:23:00"}\n'
    )
    rows = list(parse_json_lines(io.StringIO(payload)))
    assert len(rows) == 3

    _, parsed, error = rows[0]
    assert parsed is not None and error is None

    _, parsed, error = rows[1]
    assert parsed is None and error is not None
    assert "invalid json" in error.reason

    _, parsed, error = rows[2]
    assert parsed is None and error is not None


def test_parse_json_lines_skips_blank_lines() -> None:
    payload = '{"text": "Nice", "occurred_at": "2026-08-12T14:23:00"}\n\n\n'
    rows = list(parse_json_lines(io.StringIO(payload)))
    assert len(rows) == 1


def test_parse_json_array_parses_list_of_objects() -> None:
    payload = (
        '[{"text": "Nice", "occurred_at": "2026-08-12T14:23:00"}, '
        '{"text": "Bad", "occurred_at": "2026-08-12T14:24:00", "rating": 1}]'
    )
    rows = list(parse_json_array(io.StringIO(payload)))
    assert [row_number for row_number, _, _ in rows] == [1, 2]
    assert all(error is None for _, _, error in rows)


def test_parse_json_array_rejects_non_array_payload() -> None:
    rows = list(parse_json_array(io.StringIO('{"text": "Nice"}')))
    assert len(rows) == 1
    _, parsed, error = rows[0]
    assert parsed is None
    assert error is not None
    assert "array" in error.reason
