"""Data-quality gates and sample-ratio mismatch checks."""

import math
from dataclasses import dataclass

from scipy.stats import chisquare

from .errors import ValidationError
from .models import AnalysisConfig, ArmCounts, Warning, WarningSeverity


@dataclass(frozen=True)
class SRMResult:
    statistic: float
    p_value: float
    observed_share: float
    deviation: float

def exclusion_rate(arm: ArmCounts) -> float | None:
    """Return excluded records divided by received records, or None if unavailable."""
    if not isinstance(arm, ArmCounts):
        raise ValidationError("arm must be an ArmCounts value")
    return None if arm.records_received == 0 else arm.excluded_count / arm.records_received

def calculate_srm(control: ArmCounts, treatment: ArmCounts, expected_share: float) -> SRMResult | None:
    """Calculate SRM from assignment counts before outcome filtering."""
    if not isinstance(control, ArmCounts) or not isinstance(treatment, ArmCounts):
        raise ValidationError("SRM arms must be ArmCounts values")
    if not isinstance(expected_share, (int, float)) or not math.isfinite(expected_share):
        raise ValidationError("expected_share must be finite")
    if not 0 < expected_share < 1:
        raise ValidationError("expected_share must be strictly between 0 and 1")
    total = control.assignment_count + treatment.assignment_count
    if total == 0:
        return None
    observed = treatment.assignment_count / total
    expected = [total * (1 - expected_share), total * expected_share]
    result = chisquare([control.assignment_count, treatment.assignment_count], f_exp=expected)
    return SRMResult(float(result.statistic), float(result.pvalue), observed, abs(observed - expected_share))

def quality_warnings(control: ArmCounts, treatment: ArmCounts, config: AnalysisConfig) -> list[Warning]:
    """Return blocking and review warnings for record quality and SRM."""
    warnings: list[Warning] = []
    for label, arm in (("control", control), ("treatment", treatment)):
        rate = exclusion_rate(arm)
        if rate is None:
            warnings.append(Warning("records_unavailable", WarningSeverity.BLOCKING,
                f"{label} has no received records.", "records_received=0",
                "Provide assignment records for both arms."))
        elif rate > config.exclusion_tolerance:
            warnings.append(Warning("exclusion_rate_exceeded", WarningSeverity.BLOCKING,
                f"{label} exclusion rate exceeds policy.", f"rate={rate:.6g}",
                "Investigate invalid or missing records before analysis."))
        if arm.duplicate_count:
            warnings.append(Warning("duplicate_assignment", WarningSeverity.BLOCKING,
                f"{label} contains duplicate randomization units.",
                f"duplicate_count={arm.duplicate_count}", "Deduplicate or correct assignment data."))
    rates = [exclusion_rate(control), exclusion_rate(treatment)]
    if rates[0] is not None and rates[1] is not None and (
        abs(rates[0] - rates[1]) > config.missingness_difference_tolerance
    ):
        warnings.append(Warning("unequal_exclusion_rates", WarningSeverity.BLOCKING,
            "Exclusion rates differ materially between arms.", f"difference={abs(rates[0]-rates[1]):.6g}",
            "Investigate arm-specific data quality."))
    srm = calculate_srm(control, treatment, config.expected_treatment_share)
    if srm is not None and (srm.deviation > config.srm_warning_threshold
                            or srm.p_value < config.srm_blocking_p_value):
        severity = (WarningSeverity.BLOCKING if srm.p_value < config.srm_blocking_p_value
                    else WarningSeverity.WARNING)
        warnings.append(Warning(
            "srm_failure" if severity == WarningSeverity.BLOCKING else "srm_warning", severity,
            "Assignment allocation differs from the pre-specified ratio.",
            f"deviation={srm.deviation:.6g}, p_value={srm.p_value:.6g}",
            "Check randomization and assignment pipelines."))
    return warnings
