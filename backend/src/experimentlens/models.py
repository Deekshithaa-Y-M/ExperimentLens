"""Typed input, status, warning, and result models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .compat import StrEnum
from .errors import ValidationError

if TYPE_CHECKING:
    from .reliability import ReliabilityAuditContext, ReliabilityAuditResult

class Direction(StrEnum):
    HIGHER = "higher"
    LOWER = "lower"
    EITHER = "either"

MetricDirection = Direction


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class PrimaryOrSecondary(StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"

class PreRegistrationStatus(StrEnum):
    REGISTERED = "registered"
    NOT_REGISTERED = "not_registered"

class AnalysisStatus(StrEnum):
    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"
    BLOCKED = "blocked"

class DesignStatus(StrEnum):
    ADEQUATELY_POWERED = "adequately_powered"
    UNDERPOWERED = "underpowered"
    UNAVAILABLE = "unavailable"

class EvidenceStatus(StrEnum):
    SIGNIFICANT = "significant"
    NON_SIGNIFICANT = "non_significant"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNAVAILABLE = "unavailable"

class Reliability(StrEnum):
    ACCEPTABLE = "acceptable"
    REVIEW_RECOMMENDED = "review_recommended"
    BLOCKED = "blocked"

class Verdict(StrEnum):
    POSITIVE_RESULT = "positive_result"
    NEGATIVE_RESULT = "negative_result"
    INCONCLUSIVE = "inconclusive"
    STATISTICALLY_SIGNIFICANT_PRACTICALLY_WEAK = "statistically_significant_practically_weak"
    STATISTICALLY_SIGNIFICANT_PRACTICAL_IMPACT_UNCERTAIN = (
        "statistically_significant_practical_impact_uncertain"
    )
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    CANNOT_ANALYZE = "cannot_analyze"

def _probability(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise ValidationError(f"{name} must be finite")
    if not 0 < value < 1:
        raise ValidationError(f"{name} must be strictly between 0 and 1")
    return float(value)

def _count(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValidationError(f"{name} must be a non-negative integer")
    return value

@dataclass(frozen=True)
class ArmCounts:
    assignment_count: int
    records_received: int
    eligible_count: int
    success_count: int
    missing_count: int = 0
    invalid_count: int = 0
    excluded_count: int = 0
    duplicate_count: int = 0
    valid_count: int | None = None
    cross_group_count: int = 0

    def __post_init__(self) -> None:
        for name in ("assignment_count", "records_received", "eligible_count", "success_count",
                     "missing_count", "invalid_count", "excluded_count", "duplicate_count"):
            _count(getattr(self, name), name)
        _count(self.cross_group_count, "cross_group_count")
        if self.valid_count is not None:
            _count(self.valid_count, "valid_count")
        if self.success_count > self.eligible_count:
            raise ValidationError("success_count cannot exceed eligible_count")
        if self.eligible_count > self.assignment_count:
            raise ValidationError("eligible_count cannot exceed assignment_count")
        if self.assignment_count == 0 and self.eligible_count:
            raise ValidationError("eligible_count requires assigned units")
        categories = self.missing_count + self.invalid_count + self.duplicate_count
        if self.excluded_count < categories:
            raise ValidationError("excluded_count must include missing, invalid, and duplicate records")
        valid = self.eligible_count if self.valid_count is None else self.valid_count
        if valid < self.eligible_count:
            raise ValidationError("valid_count cannot be less than eligible_count")
        if valid + self.excluded_count > self.records_received:
            raise ValidationError("eligible and excluded records cannot exceed records_received")

@dataclass(frozen=True)
class AnalysisConfig:
    alpha: float = 0.05
    confidence_level: float = 0.95
    target_power: float = 0.80
    expected_treatment_share: float = 0.50
    absolute_mde: float = 0.05
    metric_direction: Direction = Direction.HIGHER
    mde_direction: Direction = Direction.EITHER
    exclusion_tolerance: float = 0.05
    missingness_difference_tolerance: float = 0.05
    srm_warning_threshold: float = 0.05
    srm_blocking_p_value: float = 0.001
    pre_registration_status: PreRegistrationStatus = PreRegistrationStatus.REGISTERED
    stopping_rule_status: str = "fixed"

    def __post_init__(self) -> None:
        for name in ("alpha", "confidence_level", "target_power", "expected_treatment_share"):
            _probability(getattr(self, name), name)
        if (isinstance(self.absolute_mde, bool) or not isinstance(self.absolute_mde, (int, float))
                or not math.isfinite(self.absolute_mde) or self.absolute_mde <= 0):
            raise ValidationError("absolute_mde must be finite and greater than zero")
        for name in ("exclusion_tolerance", "missingness_difference_tolerance",
                     "srm_warning_threshold", "srm_blocking_p_value"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 <= value < 1):
                raise ValidationError(f"{name} must be finite and in [0, 1)")
        if not isinstance(self.metric_direction, Direction):
            raise ValidationError("metric_direction is invalid")
        if not isinstance(self.mde_direction, Direction):
            raise ValidationError("mde_direction is invalid")
        if not isinstance(self.pre_registration_status, PreRegistrationStatus):
            raise ValidationError("pre_registration_status is invalid")
        if self.stopping_rule_status != "fixed":
            raise ValidationError("Version 1 only supports a fixed stopping rule")

@dataclass(frozen=True)
class BinaryExperimentInput:
    experiment_id: str
    control: ArmCounts
    treatment: ArmCounts
    config: AnalysisConfig = field(default_factory=AnalysisConfig)
    audit_context: ReliabilityAuditContext | None = None

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise ValidationError("experiment_id is required")
        if not isinstance(self.control, ArmCounts) or not isinstance(self.treatment, ArmCounts):
            raise ValidationError("exactly two ArmCounts values are required")

@dataclass(frozen=True)
class Interval:
    lower: float
    upper: float

@dataclass(frozen=True)
class Warning:
    code: str
    severity: WarningSeverity
    message: str
    evidence: str
    remediation: str

    def __post_init__(self) -> None:
        if not isinstance(self.severity, WarningSeverity):
            raise ValidationError("warning severity is invalid")

@dataclass
class AnalysisResult:
    experiment_id: str
    metric_name: str = "conversion"
    metric_type: str = "binary"
    metric_unit: str = "proportion"
    metric_direction: Direction = Direction.EITHER
    mde_direction: Direction = Direction.EITHER
    primary_or_secondary: PrimaryOrSecondary = PrimaryOrSecondary.PRIMARY
    mde_type: str = "absolute"
    absolute_mde: float | None = None
    mde_value: float | None = None
    control_label: str = "control"
    treatment_label: str = "treatment"
    randomization_unit: str = "randomization_unit"
    specification_version: str = "1.0"
    selected_method: str | None = None
    method_selection_reason: str | None = None
    control_counts: ArmCounts | None = None
    treatment_counts: ArmCounts | None = None
    expected_treatment_share: float | None = None
    observed_treatment_share: float | None = None
    allocation_deviation: float | None = None
    srm_statistic: float | None = None
    srm_p_value: float | None = None
    control_rate: float | None = None
    treatment_rate: float | None = None
    absolute_lift: float | None = None
    relative_lift: float | None = None
    control_interval: Interval | None = None
    treatment_interval: Interval | None = None
    difference_interval: Interval | None = None
    test_statistic: float | None = None
    degrees_of_freedom: int | None = None
    p_value: float | None = None
    alpha: float | None = None
    confidence_level: float | None = None
    planned_power: float | None = None
    required_control_sample_size: int | None = None
    required_treatment_sample_size: int | None = None
    design_status: DesignStatus = DesignStatus.UNAVAILABLE
    evidence_status: EvidenceStatus = EvidenceStatus.UNAVAILABLE
    analysis_status: AnalysisStatus = AnalysisStatus.BLOCKED
    reliability: Reliability = Reliability.BLOCKED
    verdict: Verdict | None = Verdict.CANNOT_ANALYZE
    warnings: list[Warning] = field(default_factory=list)
    exclusion_rates: dict[str, float | None] = field(default_factory=dict)
    records_received: dict[str, int] = field(default_factory=dict)
    eligible_counts: dict[str, int] = field(default_factory=dict)
    valid_counts: dict[str, int] = field(default_factory=dict)
    excluded_counts: dict[str, int] = field(default_factory=dict)
    missing_counts: dict[str, int] = field(default_factory=dict)
    invalid_counts: dict[str, int] = field(default_factory=dict)
    duplicate_counts: dict[str, int] = field(default_factory=dict)
    exclusion_reasons: dict[str, dict[str, int]] = field(default_factory=dict)
    pre_registration_status: PreRegistrationStatus | None = None
    stopping_rule_status: str | None = None
    reasons: list[str] = field(default_factory=list)
    planning_method: str | None = None
    planning_metadata: dict[str, Any] = field(default_factory=dict)
    reproducibility: dict[str, Any] = field(default_factory=dict)
    reliability_audit: ReliabilityAuditResult | None = None
    audit_findings: list[Any] = field(default_factory=list)
    audit_reason_codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def encode(value: Any) -> Any:
            if isinstance(value, StrEnum):
                return value.value
            if isinstance(value, Interval):
                return {"lower": value.lower, "upper": value.upper}
            if isinstance(value, ArmCounts):
                return {k: getattr(value, k) for k in value.__dataclass_fields__}
            if isinstance(value, Warning):
                return {k: encode(getattr(value, k)) for k in value.__dataclass_fields__}
            if hasattr(value, "to_dict") and callable(value.to_dict):
                return encode(value.to_dict())
            if isinstance(value, list):
                return [encode(item) for item in value]
            if isinstance(value, dict):
                return {k: encode(v) for k, v in value.items()}
            return value
        return {key: encode(value) for key, value in self.__dict__.items()}
