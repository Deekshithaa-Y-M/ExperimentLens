"""Typed models for raw ExperimentLens datasets and ingestion results."""

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .compat import StrEnum
from .errors import ValidationError
from .ingestion_errors import SchemaError
from .models import ArmCounts


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class DatasetSchema:
    required_columns: tuple[str, ...] = ("user_id", "group", "converted", "timestamp")
    optional_columns: tuple[str, ...] = (
        "revenue", "device", "country", "traffic_source", "pre_experiment_value"
    )
    user_id_column: str = "user_id"
    group_column: str = "group"
    conversion_column: str = "converted"
    timestamp_column: str = "timestamp"
    expected_group_values: tuple[str, str] = ("control", "treatment")
    timestamp_policy: str = "timezone_aware_utc"
    conversion_policy: str = "integer_0_or_1"

    def __post_init__(self) -> None:
        mapped = (
            self.user_id_column, self.group_column,
            self.conversion_column, self.timestamp_column,
        )
        if len(set(mapped)) != len(mapped):
            raise SchemaError("semantic column mappings must be distinct")
        if len(self.expected_group_values) != 2 or set(self.expected_group_values) != {
            "control", "treatment"
        }:
            raise SchemaError("Version 1 groups must be exactly control and treatment")
        if self.timestamp_policy != "timezone_aware_utc":
            raise SchemaError("only timezone_aware_utc timestamp policy is supported")
        if self.conversion_policy != "integer_0_or_1":
            raise SchemaError("only integer_0_or_1 conversion policy is supported")
        if set(self.required_columns) != set(mapped):
            raise SchemaError("required_columns must contain each mapped semantic column")


@dataclass(frozen=True)
class DatasetConfig:
    experiment_start: datetime
    experiment_end: datetime
    expected_treatment_share: float = 0.5
    schema: DatasetSchema = field(default_factory=DatasetSchema)
    duplicate_policy: str = "block_and_exclude_user"
    invalid_record_policy: str = "exclude_and_report"

    def __post_init__(self) -> None:
        for name, value in (("experiment_start", self.experiment_start),
                            ("experiment_end", self.experiment_end)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise SchemaError(f"{name} must be timezone-aware")
        start = self.experiment_start.astimezone(timezone.utc)
        end = self.experiment_end.astimezone(timezone.utc)
        if end <= start:
            raise SchemaError("experiment_end must be later than experiment_start")
        if (isinstance(self.expected_treatment_share, bool)
                or not isinstance(self.expected_treatment_share, (int, float))
                or not math.isfinite(self.expected_treatment_share)
                or not 0 < self.expected_treatment_share < 1):
            raise SchemaError("expected_treatment_share must be finite and in (0, 1)")
        if self.duplicate_policy != "block_and_exclude_user":
            raise SchemaError("only block_and_exclude_user duplicate policy is supported")
        if self.invalid_record_policy != "exclude_and_report":
            raise SchemaError("only exclude_and_report invalid record policy is supported")

    @property
    def start_utc(self) -> datetime:
        return self.experiment_start.astimezone(timezone.utc)

    @property
    def end_utc(self) -> datetime:
        return self.experiment_end.astimezone(timezone.utc)


@dataclass(frozen=True)
class DatasetIssue:
    code: str
    severity: IssueSeverity
    row_numbers: tuple[int, ...] = ()
    row_identifiers: tuple[str, ...] = ()
    affected_column: str | None = None
    message: str = ""
    evidence: str = ""
    remediation: str = ""


@dataclass(frozen=True)
class NormalizedRecord:
    row_number: int
    user_id: str
    group: str
    converted: int
    timestamp: datetime
    values: dict[str, str]


@dataclass(frozen=True)
class ArmSummary:
    assignment_count: int
    records_received: int
    eligible_count: int
    conversion_count: int
    missing_count: int
    invalid_count: int
    excluded_count: int
    duplicate_count: int
    valid_count: int
    exclusion_rate: float | None

    def to_arm_counts(self) -> ArmCounts:
        return ArmCounts(
            assignment_count=self.assignment_count,
            records_received=self.records_received,
            eligible_count=self.eligible_count,
            success_count=self.conversion_count,
            missing_count=self.missing_count,
            invalid_count=self.invalid_count,
            excluded_count=self.excluded_count,
            duplicate_count=self.duplicate_count,
            valid_count=self.valid_count,
        )


@dataclass(frozen=True)
class DatasetSummary:
    total_raw_rows: int
    rows_retained: int
    rows_excluded: int
    rows_missing_required_values: int
    rows_invalid_values: int
    rows_outside_time_window: int
    unique_assigned_users: int
    duplicate_user_count: int
    cross_group_user_count: int
    control: ArmSummary
    treatment: ArmSummary
    per_category_exclusion_counts: dict[str, int]
    per_category_exclusion_rates: dict[str, float | None]
    column_mapping: dict[str, str]
    utc_normalization_applied: bool
    dataset_hash: str

    def to_arm_counts(self) -> tuple[ArmCounts, ArmCounts]:
        return self.control.to_arm_counts(), self.treatment.to_arm_counts()


@dataclass(frozen=True)
class IngestionResult:
    summary: DatasetSummary
    normalized_records: tuple[NormalizedRecord, ...]
    issues: tuple[DatasetIssue, ...]
    has_blocking_issues: bool
    dataset_hash: str

    @property
    def issue_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for issue in self.issues:
            counts[issue.code] = counts.get(issue.code, 0) + 1
        return counts

    def preview(self, limit: int = 10) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValidationError("preview limit must be a non-negative integer")
        records = [
            {
                "row_number": record.row_number,
                "user_id": record.user_id,
                "group": record.group,
                "converted": record.converted,
                "timestamp": record.timestamp.isoformat(),
            }
            for record in self.normalized_records[:limit]
        ]
        return {
            "columns": list(self.summary.column_mapping.values()),
            "rows": records,
            "row_count": self.summary.total_raw_rows,
            "issue_counts": self.issue_counts,
        }
