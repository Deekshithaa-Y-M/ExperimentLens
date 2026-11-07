"""Structured reliability auditing for ExperimentLens analyses."""

from dataclasses import dataclass, field

from .compat import StrEnum
from .errors import ValidationError
from .models import AnalysisConfig, ArmCounts, DesignStatus, PreRegistrationStatus, Reliability
from .validation import calculate_srm, exclusion_rate


class AuditCategory(StrEnum):
    STRUCTURE = "structure"
    DUPLICATE_ASSIGNMENT = "duplicate_assignment"
    CROSS_GROUP_CONTAMINATION = "cross_group_contamination"
    SRM = "srm"
    MISSINGNESS = "missingness"
    EXCLUSION_RATE = "exclusion_rate"
    POWER = "power"
    MULTIPLE_TESTING = "multiple_testing"
    PEEKING = "peeking"
    PREREGISTRATION = "preregistration"
    STOPPING_RULE = "stopping_rule"


class AuditSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True)
class MultipleTestingContext:
    hypothesis_count: int = 1
    primary_hypothesis_count: int = 1
    primary_metric_prespecified: bool = True
    adjustment_applied: bool = False
    adjustment_method: str | None = None

    def __post_init__(self) -> None:
        for name in ("hypothesis_count", "primary_hypothesis_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValidationError(f"{name} must be a positive integer")
        if self.primary_hypothesis_count > self.hypothesis_count:
            raise ValidationError("primary_hypothesis_count cannot exceed hypothesis_count")
        if not isinstance(self.primary_metric_prespecified, bool) or not isinstance(
            self.adjustment_applied, bool
        ):
            raise ValidationError("multiple-testing flags must be boolean")
        if self.adjustment_applied and not self.adjustment_method:
            raise ValidationError("adjustment_method is required when adjustment is applied")


@dataclass(frozen=True)
class StoppingContext:
    registered_stopping_rule: str = "fixed"
    interim_looks: int = 0
    analysis_before_end_condition: bool = False
    optional_stopping_declared: bool = False
    registered_before_outcome_inspection: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.interim_looks, bool) or not isinstance(self.interim_looks, int):
            raise ValidationError("interim_looks must be a non-negative integer")
        if self.interim_looks < 0:
            raise ValidationError("interim_looks must be a non-negative integer")
        for name in (
            "analysis_before_end_condition",
            "optional_stopping_declared",
            "registered_before_outcome_inspection",
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValidationError(f"{name} must be boolean")


@dataclass(frozen=True)
class ReliabilityAuditContext:
    multiple_testing: MultipleTestingContext = field(default_factory=MultipleTestingContext)
    stopping: StoppingContext = field(default_factory=StoppingContext)
    cross_group_count: int = 0
    confirmatory: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.cross_group_count, bool) or not isinstance(self.cross_group_count, int):
            raise ValidationError("cross_group_count must be a non-negative integer")
        if self.cross_group_count < 0:
            raise ValidationError("cross_group_count must be a non-negative integer")
        if not isinstance(self.confirmatory, bool):
            raise ValidationError("confirmatory must be boolean")


@dataclass(frozen=True)
class AuditFinding:
    code: str
    category: AuditCategory
    severity: AuditSeverity
    message: str
    evidence: str
    remediation: str
    blocking: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "category": self.category.value,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
            "remediation": self.remediation,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class ReliabilityAuditResult:
    findings: tuple[AuditFinding, ...]
    overall_reliability: Reliability
    blocking: bool
    review_recommended: bool
    categories_checked: tuple[AuditCategory, ...]
    summary: str
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "findings": [finding.to_dict() for finding in self.findings],
            "overall_reliability": self.overall_reliability.value,
            "blocking": self.blocking,
            "review_recommended": self.review_recommended,
            "categories_checked": [category.value for category in self.categories_checked],
            "summary": self.summary,
            "metadata": dict(self.metadata),
            "reason_codes": list(self.reason_codes),
        }


def _finding(
    code: str,
    category: AuditCategory,
    severity: AuditSeverity,
    message: str,
    evidence: str,
    remediation: str,
    *,
    blocking: bool | None = None,
) -> AuditFinding:
    return AuditFinding(
        code, category, severity, message, evidence, remediation,
        severity == AuditSeverity.BLOCKING if blocking is None else blocking,
    )


def audit_reliability(
    control: ArmCounts,
    treatment: ArmCounts,
    config: AnalysisConfig,
    *,
    context: ReliabilityAuditContext | None = None,
    design_status: DesignStatus = DesignStatus.UNAVAILABLE,
    planning_error: str | None = None,
) -> ReliabilityAuditResult:
    """Audit reliability controls without changing statistical calculations."""
    if not isinstance(control, ArmCounts) or not isinstance(treatment, ArmCounts):
        raise ValidationError("audit arms must be ArmCounts values")
    if not isinstance(config, AnalysisConfig):
        raise ValidationError("audit config must be an AnalysisConfig value")
    context = ReliabilityAuditContext() if context is None else context
    findings: list[AuditFinding] = []

    for label, arm in (("control", control), ("treatment", treatment)):
        if arm.records_received == 0:
            findings.append(_finding(
                "records_unavailable", AuditCategory.STRUCTURE, AuditSeverity.BLOCKING,
                f"{label} has no received records.", "records_received=0",
                "Provide received records for both arms.",
            ))
        if arm.missing_count or arm.invalid_count:
            findings.append(_finding(
                "missing_or_invalid_records", AuditCategory.MISSINGNESS, AuditSeverity.WARNING,
                f"{label} contains missing or invalid records.",
                f"missing_count={arm.missing_count}, invalid_count={arm.invalid_count}",
                "Investigate source data and exclusion causes.",
            ))
        rate = exclusion_rate(arm)
        if rate is not None and rate > config.exclusion_tolerance:
            findings.append(_finding(
                "exclusion_rate_exceeded", AuditCategory.EXCLUSION_RATE, AuditSeverity.BLOCKING,
                f"{label} exclusion rate exceeds policy.", f"rate={rate:.6g}",
                "Investigate and correct excluded records before confirmatory use.",
            ))
        if arm.duplicate_count:
            findings.append(_finding(
                "duplicate_assignment", AuditCategory.DUPLICATE_ASSIGNMENT, AuditSeverity.BLOCKING,
                f"{label} contains duplicate assignments.",
                f"duplicate_count={arm.duplicate_count}",
                "Deduplicate or correct assignment data.",
            ))

    control_rate = exclusion_rate(control)
    treatment_rate = exclusion_rate(treatment)
    if control_rate is not None and treatment_rate is not None:
        difference = abs(control_rate - treatment_rate)
        if difference > config.missingness_difference_tolerance:
            findings.append(_finding(
                "unequal_exclusion_rates", AuditCategory.MISSINGNESS, AuditSeverity.BLOCKING,
                "Exclusion rates differ materially between arms.",
                f"difference={difference:.6g}",
                "Investigate arm-specific data quality.",
            ))

    if context.cross_group_count:
        severity = AuditSeverity.BLOCKING if context.confirmatory else AuditSeverity.WARNING
        findings.append(_finding(
            "cross_group_contamination", AuditCategory.CROSS_GROUP_CONTAMINATION, severity,
            "Users were observed in both experiment groups.",
            f"cross_group_count={context.cross_group_count}",
            "Correct assignment contamination before confirmatory interpretation.",
        ))

    srm = calculate_srm(control, treatment, config.expected_treatment_share)
    if srm is not None:
        if srm.p_value < config.srm_blocking_p_value:
            findings.append(_finding(
                "srm_failure", AuditCategory.SRM, AuditSeverity.BLOCKING,
                "Assignment allocation fails the SRM blocking threshold.",
                f"observed_share={srm.observed_share:.6g}, deviation={srm.deviation:.6g}, "
                f"p_value={srm.p_value:.6g}",
                "Check the randomization and assignment pipelines.",
            ))
        elif srm.deviation > config.srm_warning_threshold:
            findings.append(_finding(
                "srm_warning", AuditCategory.SRM, AuditSeverity.WARNING,
                "Assignment allocation differs from the pre-specified ratio.",
                f"observed_share={srm.observed_share:.6g}, deviation={srm.deviation:.6g}, "
                f"p_value={srm.p_value:.6g}",
                "Review randomization before interpreting the result.",
            ))

    if planning_error is not None:
        findings.append(_finding(
            "power_planning_unavailable", AuditCategory.POWER, AuditSeverity.WARNING,
            "Power planning is unavailable for this baseline or configuration.",
            planning_error, "Review baseline rate, MDE, and allocation.",
        ))
    elif design_status == DesignStatus.UNDERPOWERED:
        findings.append(_finding(
            "underpowered", AuditCategory.POWER, AuditSeverity.WARNING,
            "The observed sample is below the planned design requirement.",
            "observed sample size is below the required sample size",
            "Treat the result as review-recommended and avoid an unqualified recommendation.",
        ))
    elif design_status == DesignStatus.UNAVAILABLE:
        findings.append(_finding(
            "power_unavailable", AuditCategory.POWER, AuditSeverity.WARNING,
            "Power status is unavailable.", "design_status=unavailable",
            "Review whether a valid planning baseline and MDE are available.",
        ))

    multiple = context.multiple_testing
    multiple_issue = multiple.hypothesis_count > 1 or multiple.primary_hypothesis_count > 1
    if multiple_issue and not multiple.adjustment_applied:
        if context.confirmatory:
            code = (
                "multiple_primary_hypotheses"
                if multiple.primary_hypothesis_count > 1
                else "multiple_testing_not_declared"
            )
            findings.append(_finding(
                code, AuditCategory.MULTIPLE_TESTING, AuditSeverity.BLOCKING,
                "Multiple hypotheses were tested without a declared adjustment.",
                f"hypothesis_count={multiple.hypothesis_count}, "
                f"primary_hypothesis_count={multiple.primary_hypothesis_count}",
                "Declare the multiplicity or restrict confirmatory interpretation.",
            ))
        else:
            findings.append(_finding(
                "exploratory_multiple_testing", AuditCategory.MULTIPLE_TESTING,
                AuditSeverity.WARNING,
                "Multiple exploratory hypotheses were reported without adjustment.",
                f"hypothesis_count={multiple.hypothesis_count}",
                "Report as exploratory and avoid an unqualified confirmatory verdict.",
            ))
    if context.confirmatory and not multiple.primary_metric_prespecified:
        findings.append(_finding(
            "primary_metric_not_prespecified", AuditCategory.PREREGISTRATION,
            AuditSeverity.BLOCKING,
            "The primary metric was not pre-specified.",
            "primary_metric_prespecified=false",
            "Register the primary metric before outcome inspection.",
        ))

    stopping = context.stopping
    stopping_issues: list[tuple[str, str, str]] = []
    if stopping.registered_stopping_rule != "fixed":
        stopping_issues.append(("stopping_rule_not_fixed", "registered rule is not fixed",
                                "Register a fixed stopping rule for confirmatory analysis."))
    if stopping.interim_looks > 0:
        stopping_issues.append(("unauthorized_interim_look",
                                f"interim_looks={stopping.interim_looks}",
                                "Do not inspect outcomes before the registered end condition."))
    if stopping.analysis_before_end_condition or stopping.optional_stopping_declared:
        stopping_issues.append(("optional_stopping_detected", "optional stopping or early analysis detected",
                                "Complete the fixed stopping rule before confirmatory interpretation."))
    if not stopping.registered_before_outcome_inspection:
        stopping_issues.append(("preregistration_missing",
                                "registered_before_outcome_inspection=false",
                                "Register the analysis before inspecting outcomes."))
    for code, evidence, remediation in stopping_issues:
        severity = AuditSeverity.BLOCKING if context.confirmatory else AuditSeverity.WARNING
        category = (
            AuditCategory.PREREGISTRATION
            if code == "preregistration_missing"
            else AuditCategory.PEEKING
            if code in {"unauthorized_interim_look", "optional_stopping_detected"}
            else AuditCategory.STOPPING_RULE
        )
        findings.append(_finding(
            code, category, severity, "Confirmatory stopping controls were not satisfied.",
            evidence, remediation,
        ))
    if context.confirmatory and config.pre_registration_status != PreRegistrationStatus.REGISTERED:
        findings.append(_finding(
            "preregistration_missing", AuditCategory.PREREGISTRATION, AuditSeverity.BLOCKING,
            "Confirmatory analysis requires pre-registration.",
            f"pre_registration_status={config.pre_registration_status.value}",
            "Register the analysis before outcome inspection.",
        ))

    findings.sort(key=lambda finding: (finding.category.value, finding.code))
    blocking = any(finding.blocking for finding in findings)
    review = any(finding.severity == AuditSeverity.WARNING for finding in findings)
    reliability = (
        Reliability.BLOCKED if blocking
        else Reliability.REVIEW_RECOMMENDED if review
        else Reliability.ACCEPTABLE
    )
    categories = tuple(AuditCategory)
    summary = (
        "Reliability audit blocked analysis."
        if blocking else "Reliability review is recommended."
        if review else "Reliability audit passed."
    )
    return ReliabilityAuditResult(
        tuple(findings), reliability, blocking, review, categories, summary,
        metadata={
            "expected_treatment_share": config.expected_treatment_share,
            "observed_treatment_share": None if srm is None else srm.observed_share,
            "allocation_deviation": None if srm is None else srm.deviation,
            "srm_p_value": None if srm is None else srm.p_value,
        },
    )
