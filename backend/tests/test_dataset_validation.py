from datetime import datetime, timezone

import pytest

from experimentlens.dataset_models import DatasetConfig, DatasetSchema
from experimentlens.dataset_validation import parse_conversion, parse_timestamp, timestamp_in_window
from experimentlens.ingestion_errors import SchemaError


def config():
    return DatasetConfig(
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def test_strict_conversion_and_timestamp_policies():
    assert parse_conversion("0") == 0
    assert parse_conversion("1") == 1
    for value in ("", "yes", "no", "true", "false", "1.0", "0.5"):
        assert parse_conversion(value) is None
    normalized = parse_timestamp("2026-01-01T01:00:00+01:00")
    assert normalized == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert parse_timestamp("2026-01-01T00:00:00") is None
    assert parse_timestamp("not-a-timestamp") is None


def test_half_open_window_boundaries():
    settings = config()
    start = parse_timestamp("2026-01-01T00:00:00Z")
    end = parse_timestamp("2026-01-02T00:00:00Z")
    assert start is not None and end is not None
    assert timestamp_in_window(start, settings)
    assert not timestamp_in_window(end, settings)


def test_config_rejects_naive_and_reversed_windows():
    with pytest.raises(SchemaError):
        DatasetConfig(datetime(2026, 1, 1), datetime(2026, 1, 2))
    with pytest.raises(SchemaError):
        DatasetConfig(
            datetime(2026, 1, 2, tzinfo=timezone.utc),
            datetime(2026, 1, 1, tzinfo=timezone.utc),
        )


def test_schema_rejects_ambiguous_mapping():
    with pytest.raises(SchemaError):
        DatasetSchema(group_column="user_id")

