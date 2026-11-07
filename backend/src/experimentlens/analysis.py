"""End-to-end deterministic binary experiment analysis."""

from .decisions import verdict_for
from .errors import ValidationError
from .intervals import newcombe_interval, wilson_interval
from .metrics import absolute_lift, conversion_rate, relative_lift
from .models import (
    AnalysisResult,
    AnalysisStatus,
    BinaryExperimentInput,
    DesignStatus,
    EvidenceStatus,
    PreRegistrationStatus,
    Reliability,
    Verdict,
    Warning,
    WarningSeverity,
)
from .power import (
    ALLOCATION_TOLERANCE_FACTOR,
    PAIR_SEARCH_MAX_TOTAL,
    design_status,
    required_sample_sizes,
)
from .reliability import ReliabilityAuditContext, audit_reliability
from .tests import two_proportion_test
from .validation import calculate_srm, exclusion_rate, quality_warnings


def _planning_warning(message: str) -> Warning:
    return Warning(
        "planning_unavailable",
        WarningSeverity.WARNING,
        "Power planning is unavailable for this baseline and configuration.",
        message,
        "Review the baseline, MDE, and allocation before interpreting design status.",
    )


def analyze(experiment: BinaryExperimentInput) -> AnalysisResult:
    """Analyze a registered or exploratory two-arm binary experiment."""
    if not isinstance(experiment, BinaryExperimentInput):
        raise ValidationError("experiment must be a BinaryExperimentInput")
    c, t, cfg = experiment.control, experiment.treatment, experiment.config
    result = AnalysisResult(
        experiment.experiment_id,
        metric_direction=cfg.metric_direction,
        mde_direction=cfg.mde_direction,
        absolute_mde=cfg.absolute_mde,
        mde_value=cfg.absolute_mde,
        control_counts=c,
        treatment_counts=t,
        alpha=cfg.alpha,
        confidence_level=cfg.confidence_level,
        planned_power=cfg.target_power,
        expected_treatment_share=cfg.expected_treatment_share,
        pre_registration_status=cfg.pre_registration_status,
        stopping_rule_status=cfg.stopping_rule_status,
        records_received={"control": c.records_received, "treatment": t.records_received},
        eligible_counts={"control": c.eligible_count, "treatment": t.eligible_count},
        valid_counts={
            "control": c.eligible_count if c.valid_count is None else c.valid_count,
            "treatment": t.eligible_count if t.valid_count is None else t.valid_count,
        },
        excluded_counts={"control": c.excluded_count, "treatment": t.excluded_count},
        missing_counts={"control": c.missing_count, "treatment": t.missing_count},
        invalid_counts={"control": c.invalid_count, "treatment": t.invalid_count},
        duplicate_counts={"control": c.duplicate_count, "treatment": t.duplicate_count},
        exclusion_reasons={
            "control": {"missing": c.missing_count, "invalid": c.invalid_count,
                        "duplicate": c.duplicate_count},
            "treatment": {"missing": t.missing_count, "invalid": t.invalid_count,
                          "duplicate": t.duplicate_count},
        },
        reproducibility={
            "deterministic": True,
            "random_seed": None,
            "specification_version": "1.0",
        },
    )
    result.exclusion_rates = {"control": exclusion_rate(c), "treatment": exclusion_rate(t)}
    result.warnings = quality_warnings(c, t, cfg)
    planning_error: str | None = None

    srm = calculate_srm(c, t, cfg.expected_treatment_share)
    if srm is not None:
        result.observed_treatment_share = srm.observed_share
        result.allocation_deviation = srm.deviation
        result.srm_statistic, result.srm_p_value = srm.statistic, srm.p_value

    result.control_rate = conversion_rate(c.success_count, c.eligible_count)
    result.treatment_rate = conversion_rate(t.success_count, t.eligible_count)
    if result.control_rate is None or result.treatment_rate is None:
        result.reasons.append("Both arms require at least one eligible unit.")
    else:
        result.absolute_lift = absolute_lift(result.control_rate, result.treatment_rate)
        result.relative_lift = relative_lift(result.control_rate, result.treatment_rate)
        result.control_interval = wilson_interval(c.success_count, c.eligible_count, cfg.confidence_level)
        result.treatment_interval = wilson_interval(t.success_count, t.eligible_count, cfg.confidence_level)
        result.difference_interval = newcombe_interval(
            c.success_count, c.eligible_count, t.success_count, t.eligible_count,
            cfg.confidence_level,
        )
        try:
            required = required_sample_sizes(result.control_rate, cfg)
        except ValidationError as exc:
            planning_error = str(exc)
            result.warnings.append(_planning_warning(str(exc)))
        else:
            result.required_control_sample_size, result.required_treatment_sample_size = required
            result.planning_method = (
                "normal_approximation_formula" if cfg.expected_treatment_share == 0.5
                else "integer_pair_power_search"
            )
            result.planning_metadata = {
                "baseline_rate": result.control_rate,
                "treatment_rate_at_mde": (
                    result.control_rate + cfg.absolute_mde
                    if cfg.mde_direction.value != "lower"
                    else result.control_rate - cfg.absolute_mde
                ),
                "target_power": cfg.target_power,
                "allocation_share": cfg.expected_treatment_share,
                "allocation_tolerance": ALLOCATION_TOLERANCE_FACTOR / (
                    result.required_control_sample_size + result.required_treatment_sample_size
                ),
                "search_max_total": PAIR_SEARCH_MAX_TOTAL,
                "either_direction_planning": "higher",
            }
            result.design_status = design_status(c.eligible_count, t.eligible_count, required)
        if result.difference_interval is not None:
            test = two_proportion_test(
                c.success_count, c.eligible_count, t.success_count, t.eligible_count
            )
            result.selected_method = test.method
            result.method_selection_reason = test.reason
            result.test_statistic = test.statistic
            result.p_value = test.p_value
            result.degrees_of_freedom = test.degrees_of_freedom

    audit_context = experiment.audit_context
    if audit_context is None:
        audit_context = ReliabilityAuditContext(
            confirmatory=cfg.pre_registration_status == PreRegistrationStatus.REGISTERED
        )
    result.reliability_audit = audit_reliability(
        c,
        t,
        cfg,
        context=audit_context,
        design_status=result.design_status,
        planning_error=planning_error,
    )
    result.audit_findings = list(result.reliability_audit.findings)
    result.audit_reason_codes = list(result.reliability_audit.reason_codes)

    blocking = (
        any(w.severity == WarningSeverity.BLOCKING for w in result.warnings)
        or bool(result.reasons)
        or result.reliability_audit.blocking
    )
    if blocking:
        result.analysis_status = AnalysisStatus.BLOCKED
        result.reliability = Reliability.BLOCKED
        result.verdict = Verdict.CANNOT_ANALYZE
        result.evidence_status = EvidenceStatus.UNAVAILABLE
        return result

    result.reliability = result.reliability_audit.overall_reliability
    if result.p_value is None or result.absolute_lift is None or result.difference_interval is None:
        result.evidence_status = EvidenceStatus.UNAVAILABLE
        return result
    result.analysis_status, result.evidence_status, result.verdict = verdict_for(
        result.p_value,
        result.absolute_lift,
        result.difference_interval,
        cfg,
        cfg.pre_registration_status.value != "registered",
        result.design_status == DesignStatus.UNDERPOWERED,
        result.reliability,
    )
    if result.design_status == DesignStatus.UNAVAILABLE:
        result.evidence_status = EvidenceStatus.UNAVAILABLE
    return result
