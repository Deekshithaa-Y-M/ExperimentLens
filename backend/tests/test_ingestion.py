from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import pytest

from experimentlens import BinaryExperimentInput, analyze
from experimentlens.dataset_models import DatasetConfig, DatasetSchema, IssueSeverity
from experimentlens.ingestion import ingest_csv
from experimentlens.ingestion_errors import SchemaError

WINDOW = DatasetConfig(
    datetime(2026, 1, 1, tzinfo=timezone.utc),
    datetime(2026, 1, 2, tzinfo=timezone.utc),
)


def csv_data(rows):
    return StringIO(
        "user_id,group,converted,timestamp,device,extra\n"
        + "\n".join(f"{user},{group},{converted},{timestamp},web,kept" for
                    user, group, converted, timestamp in rows)
        + "\n"
    )


def test_valid_ingestion_maps_to_arm_counts_and_analysis():
    result = ingest_csv(csv_data([
        ("c1", "control", "0", "2026-01-01T00:00:00Z"),
        ("c2", "control", "1", "2026-01-01T01:00:00Z"),
        ("t1", "treatment", "1", "2026-01-01T01:00:00+01:00"),
        ("t2", "treatment", "0", "2026-01-01T02:00:00Z"),
    ]), WINDOW)
    control, treatment = result.summary.to_arm_counts()
    assert (control.assignment_count, treatment.assignment_count) == (2, 2)
    assert (control.eligible_count, treatment.eligible_count) == (2, 2)
    assert (control.success_count, treatment.success_count) == (1, 1)
    assert result.summary.total_raw_rows == 4
    assert result.summary.rows_retained == 4
    assert any(issue.code == "unknown_columns" for issue in result.issues)
    analyzed = analyze(BinaryExperimentInput("ingested", control, treatment))
    assert analyzed.srm_p_value is not None


def test_realistic_csv_fixture_is_ingested():
    fixture = Path(__file__).parent / "fixtures" / "valid_experiment.csv"
    result = ingest_csv(fixture, WINDOW)
    assert result.summary.total_raw_rows == 4
    assert result.summary.control.eligible_count == 2
    assert result.summary.treatment.eligible_count == 2


def test_custom_column_mapping_and_timezone_normalization():
    schema = DatasetSchema(
        required_columns=("id", "arm", "outcome", "at"),
        user_id_column="id",
        group_column="arm",
        conversion_column="outcome",
        timestamp_column="at",
    )
    config = DatasetConfig(WINDOW.experiment_start, WINDOW.experiment_end, schema=schema)
    result = ingest_csv(StringIO(
        "id,arm,outcome,at\nu1,control,1,2026-01-01T01:00:00+01:00\n"
    ), config)
    assert result.normalized_records[0].timestamp == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert result.summary.column_mapping["user_id"] == "id"


def test_missing_columns_and_zero_rows_are_explicit():
    with pytest.raises(SchemaError):
        ingest_csv(StringIO("user_id,group,converted\nu1,control,1\n"), WINDOW)
    result = ingest_csv(StringIO("user_id,group,converted,timestamp\n"), WINDOW)
    assert result.summary.total_raw_rows == 0
    assert result.summary.control.assignment_count == 0
    assert not result.has_blocking_issues


def test_invalid_values_are_reported_and_not_counted_as_assignments():
    result = ingest_csv(csv_data([
        ("", "control", "1", "2026-01-01T00:00:00Z"),
        ("bad-group", "variant", "1", "2026-01-01T00:00:00Z"),
        ("bad-conversion", "control", "yes", "2026-01-01T00:00:00Z"),
        ("fraction", "treatment", "0.5", "2026-01-01T00:00:00Z"),
        ("bad-time", "treatment", "1", "2026-01-01T00:00:00"),
    ]), WINDOW)
    codes = {issue.code for issue in result.issues}
    assert {"missing_required_value", "invalid_group", "invalid_conversion",
            "invalid_timestamp"} <= codes
    assert result.summary.control.assignment_count == 1
    assert result.summary.control.eligible_count == 0
    assert result.has_blocking_issues


def test_duplicate_and_cross_group_users_are_blocking_and_not_eligible():
    result = ingest_csv(csv_data([
        ("duplicate", "control", "1", "2026-01-01T00:00:00Z"),
        ("duplicate", "control", "0", "2026-01-01T01:00:00Z"),
        ("contaminated", "control", "1", "2026-01-01T00:00:00Z"),
        ("contaminated", "treatment", "1", "2026-01-01T01:00:00Z"),
        ("valid", "treatment", "0", "2026-01-01T01:00:00Z"),
    ]), WINDOW)
    assert result.summary.duplicate_user_count == 1
    assert result.summary.cross_group_user_count == 1
    assert result.summary.control.eligible_count == 0
    assert result.summary.treatment.eligible_count == 1
    assert {issue.code for issue in result.issues} >= {"duplicate_user", "cross_group_user"}
    assert all(issue.severity == IssueSeverity.BLOCKING for issue in result.issues
               if issue.code in {"duplicate_user", "cross_group_user"})


def test_cross_group_rows_are_counted_in_both_arm_exclusions():
    result = ingest_csv(csv_data([
        ("contaminated", "control", "1", "2026-01-01T00:00:00Z"),
        ("contaminated", "treatment", "1", "2026-01-01T01:00:00Z"),
        ("control-only", "control", "0", "2026-01-01T02:00:00Z"),
        ("treatment-only", "treatment", "0", "2026-01-01T02:00:00Z"),
    ]), WINDOW)
    assert any(issue.code == "cross_group_user" for issue in result.issues)
    assert result.summary.per_category_exclusion_counts["cross_group"] == 2
    assert result.summary.control.excluded_count == 1
    assert result.summary.treatment.excluded_count == 1
    assert result.summary.control.exclusion_rate == pytest.approx(0.5)
    assert result.summary.treatment.exclusion_rate == pytest.approx(0.5)
    assert result.summary.control.eligible_count == 1
    assert result.summary.treatment.eligible_count == 1
    assert result.summary.control.conversion_count == 0
    assert result.summary.treatment.conversion_count == 0


def test_exclusion_categories_sum_to_rows_excluded_with_precedence():
    result = ingest_csv(csv_data([
        ("", "control", "yes", "not-a-time"),  # missing wins
        ("invalid", "unknown", "0.5", "not-a-time"),  # invalid wins
        ("outside", "control", "0", "2025-12-31T23:59:00Z"),
        ("duplicate", "control", "0", "2026-01-01T00:00:00Z"),
        ("duplicate", "control", "1", "2026-01-01T01:00:00Z"),
        ("cross", "control", "1", "2026-01-01T02:00:00Z"),
        ("cross", "treatment", "0", "2026-01-01T03:00:00Z"),
        ("valid", "treatment", "0", "2026-01-01T04:00:00Z"),
    ]), WINDOW)
    counts = result.summary.per_category_exclusion_counts
    assert sum(counts.values()) == result.summary.rows_excluded
    assert result.summary.rows_excluded == (
        result.summary.total_raw_rows - result.summary.rows_retained
    )
    assert counts == {
        "missing": 1,
        "invalid": 1,
        "outside_window": 1,
        "duplicate": 2,
        "cross_group": 2,
    }


def test_time_window_and_preview_are_deterministic():
    result = ingest_csv(csv_data([
        ("at-start", "control", "1", "2026-01-01T00:00:00Z"),
        ("at-end", "control", "1", "2026-01-02T00:00:00Z"),
    ]), WINDOW)
    assert result.summary.rows_outside_time_window == 1
    assert result.summary.control.eligible_count == 1
    assert len(result.preview(1)["rows"]) == 1
    assert result.preview(1) == result.preview(1)
    with pytest.raises(ValueError):
        result.preview(-1)
