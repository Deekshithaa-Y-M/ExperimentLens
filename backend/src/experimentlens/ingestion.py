"""CSV ingestion into validated, auditable binary experiment summaries."""

import csv
import hashlib
import io
from collections import Counter, defaultdict
from pathlib import Path
from typing import TextIO, TypedDict

from .dataset_models import (
    ArmSummary,
    DatasetConfig,
    DatasetIssue,
    DatasetSummary,
    IngestionResult,
    IssueSeverity,
    NormalizedRecord,
)
from .dataset_validation import parse_conversion, parse_timestamp, timestamp_in_window
from .ingestion_errors import SchemaError, UnreadableInputError


class _RowData(TypedDict):
    row_number: int
    user: str
    group: str
    valid_assignment: bool
    category: str


def _source_stream(source: TextIO | str | Path) -> tuple[TextIO, bool]:
    if hasattr(source, "read"):
        return source, False  # type: ignore[return-value]
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source):
        try:
            return open(source, "r", newline="", encoding="utf-8"), True
        except OSError as exc:
            raise UnreadableInputError("unable to read CSV input") from exc
    if isinstance(source, str):
        return io.StringIO(source), True
    raise UnreadableInputError("CSV input must be a text stream, string, or path")


def ingest_csv(source: TextIO | str | Path, config: DatasetConfig) -> IngestionResult:
    """Read CSV rows from a stream or file and produce a deterministic summary."""
    stream, should_close = _source_stream(source)
    try:
        try:
            reader = csv.DictReader(stream)
            fieldnames = reader.fieldnames
            if fieldnames is None:
                raise SchemaError("CSV input must contain a header")
            fields = tuple(fieldnames)
            required = config.schema.required_columns
            missing = tuple(column for column in required if column not in fields)
            if missing:
                raise SchemaError(f"missing required columns: {', '.join(missing)}")
            issues: list[DatasetIssue] = []
            known = set(required) | set(config.schema.optional_columns)
            unknown = tuple(column for column in fields if column not in known)
            if unknown:
                issues.append(DatasetIssue(
                    "unknown_columns", IssueSeverity.INFO, affected_column=",".join(unknown),
                    message="Unknown columns were preserved in normalized input.",
                    evidence=",".join(unknown), remediation="Review extra columns if they are needed.",
                ))
            rows = list(reader)
        except csv.Error as exc:
            raise UnreadableInputError("malformed CSV input") from exc
    finally:
        if should_close:
            stream.close()

    row_data: list[_RowData] = []
    candidate_records: dict[int, NormalizedRecord] = {}
    for row_number, raw in enumerate(rows, start=2):
        user = (raw.get(config.schema.user_id_column) or "").strip()
        group = (raw.get(config.schema.group_column) or "").strip()
        conversion_text = raw.get(config.schema.conversion_column) or ""
        timestamp_text = raw.get(config.schema.timestamp_column) or ""
        missing_columns = tuple(
            column for column, value in (
                (config.schema.user_id_column, user),
                (config.schema.group_column, group),
                (config.schema.conversion_column, conversion_text),
                (config.schema.timestamp_column, timestamp_text),
            ) if not value.strip()
        )
        timestamp = parse_timestamp(timestamp_text)
        conversion = parse_conversion(conversion_text)
        valid_group = group in config.schema.expected_group_values
        valid_timestamp = timestamp is not None
        in_window = (
            timestamp is not None
            and timestamp_in_window(timestamp, config)
        )
        if missing_columns:
            category = "missing"
            code = "missing_required_value"
            issues.append(DatasetIssue(
                code, IssueSeverity.BLOCKING, (row_number,), (user,) if user else (),
                ",".join(missing_columns), "Required value is missing.",
                ",".join(missing_columns), "Populate all required columns.",
            ))
        elif not valid_group:
            category = "invalid"
            code = "invalid_group"
            issues.append(DatasetIssue(
                code, IssueSeverity.BLOCKING, (row_number,), (user,),
                config.schema.group_column, "Group is not control or treatment.", group,
                "Use exactly control or treatment.",
            ))
        elif not valid_timestamp:
            category = "invalid"
            code = "invalid_timestamp"
            issues.append(DatasetIssue(
                code, IssueSeverity.BLOCKING, (row_number,), (user,),
                config.schema.timestamp_column, "Timestamp must be valid and timezone-aware.",
                timestamp_text, "Provide an ISO timestamp with an explicit timezone.",
            ))
        elif not in_window:
            category = "outside_window"
            code = "outside_time_window"
            issues.append(DatasetIssue(
                code, IssueSeverity.WARNING, (row_number,), (user,),
                config.schema.timestamp_column, "Row is outside the half-open experiment window.",
                timestamp_text, "Restrict the input to the registered experiment window.",
            ))
        elif conversion is None:
            category = "invalid"
            code = "invalid_conversion"
            issues.append(DatasetIssue(
                code, IssueSeverity.BLOCKING, (row_number,), (user,),
                config.schema.conversion_column, "Conversion must be literal 0 or 1.",
                conversion_text, "Use integer binary conversion values.",
            ))
        elif timestamp is not None:
            category = ""
            code = ""
            candidate_records[row_number] = NormalizedRecord(
                row_number, user, group, conversion, timestamp, dict(raw)
            )
        else:
            category = "invalid"
            code = "invalid_timestamp"
        row_data.append({
            "row_number": row_number, "user": user, "group": group,
            "valid_assignment": bool(user and valid_group and in_window),
            "category": category,
        })

    users_by_group: dict[str, set[str]] = defaultdict(set)
    for item in row_data:
        if item["valid_assignment"]:
            users_by_group[str(item["group"])].add(str(item["user"]))
    cross_users = users_by_group["control"] & users_by_group["treatment"]
    user_rows: dict[str, list[_RowData]] = defaultdict(list)
    for item in row_data:
        if item["valid_assignment"]:
            user_rows[str(item["user"])].append(item)
    duplicate_users = {
        user for user, items in user_rows.items()
        if any(
            sum(1 for item in items if item["group"] == group) > 1
            for group in ("control", "treatment")
        )
    }
    if duplicate_users:
        issues.append(DatasetIssue(
            "duplicate_user", IssueSeverity.BLOCKING,
            row_identifiers=tuple(sorted(duplicate_users)),
            message="Users have multiple in-window assignment rows.",
            evidence=f"count={len(duplicate_users)}",
            remediation="Remove duplicate randomization records before confirmatory analysis.",
        ))
    if cross_users:
        issues.append(DatasetIssue(
            "cross_group_user", IssueSeverity.BLOCKING,
            row_identifiers=tuple(sorted(cross_users)),
            message="Users appear in both control and treatment.",
            evidence=f"count={len(cross_users)}",
            remediation="Correct assignment contamination before confirmatory analysis.",
        ))

    # Apply the remaining row-level categories only to otherwise valid rows.
    # Precedence: missing, invalid, outside_window, duplicate, cross_group.
    for item in row_data:
        if item["category"] != "" or not item["valid_assignment"]:
            continue
        user = str(item["user"])
        if user in duplicate_users:
            item["category"] = "duplicate"
        elif user in cross_users:
            item["category"] = "cross_group"

    category_counts: Counter[str] = Counter(
        str(item["category"]) for item in row_data if item["category"]
    )
    normalized = [
        candidate_records[int(item["row_number"])]
        for item in row_data
        if item["category"] == ""
    ]
    arm_summaries: dict[str, ArmSummary] = {}
    retained_records: list[NormalizedRecord] = []
    for arm in ("control", "treatment"):
        arm_rows = [item for item in row_data if item["group"] == arm]
        arm_users = {
            str(item["user"]) for item in arm_rows if item["valid_assignment"]
        } - cross_users
        eligible_rows = [
            candidate_records[int(item["row_number"])]
            for item in arm_rows
            if item["category"] == ""
        ]
        eligible_users = {item.user_id for item in eligible_rows}
        assignment_count = len(arm_users)
        duplicate_count = sum(
            1 for item in arm_rows
            if item["category"] == "duplicate"
        )
        missing_count = sum(1 for item in arm_rows if item["category"] == "missing")
        invalid_count = sum(1 for item in arm_rows if item["category"] == "invalid")
        outside_count = sum(1 for item in arm_rows if item["category"] == "outside_window")
        cross_group_count = sum(1 for item in arm_rows if item["category"] == "cross_group")
        excluded_count = (
            missing_count + invalid_count + outside_count
            + duplicate_count + cross_group_count
        )
        conversion_count = sum(item.converted for item in eligible_rows)
        retained_records.extend(eligible_rows)
        records_received = len(arm_rows)
        arm_summaries[arm] = ArmSummary(
            assignment_count, records_received, len(eligible_users), conversion_count,
            missing_count, invalid_count, excluded_count, duplicate_count, len(eligible_users),
            excluded_count / records_received if records_received else None,
        )

    payload = "\n".join(
        f"{record.row_number}|{record.user_id}|{record.group}|{record.converted}|"
        f"{record.timestamp.isoformat()}" for record in sorted(retained_records, key=lambda x: x.row_number)
    ).encode()
    dataset_hash = hashlib.sha256(payload).hexdigest()
    total = len(rows)
    retained = len(normalized)
    per_counts = {
        "missing": category_counts["missing"],
        "invalid": category_counts["invalid"],
        "outside_window": category_counts["outside_window"],
        "duplicate": sum(item.duplicate_count for item in arm_summaries.values()),
        "cross_group": category_counts["cross_group"],
    }
    per_rates = {key: value / total if total else None for key, value in per_counts.items()}
    summary = DatasetSummary(
        total, retained, total - retained, per_counts["missing"], per_counts["invalid"],
        per_counts["outside_window"], len(set().union(*users_by_group.values())),
        len(duplicate_users), len(cross_users),
        arm_summaries["control"],
        arm_summaries["treatment"], per_counts, per_rates,
        {
            "user_id": config.schema.user_id_column,
            "group": config.schema.group_column,
            "converted": config.schema.conversion_column,
            "timestamp": config.schema.timestamp_column,
        },
        True, dataset_hash,
    )
    blocking = any(issue.severity == IssueSeverity.BLOCKING for issue in issues)
    return IngestionResult(summary, tuple(retained_records), tuple(issues), blocking, dataset_hash)
