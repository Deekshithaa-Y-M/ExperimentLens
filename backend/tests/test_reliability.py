import pytest

from experimentlens import (
    AnalysisConfig,
    ArmCounts,
    BinaryExperimentInput,
    PreRegistrationStatus,
    analyze,
)
from experimentlens.errors import ValidationError
from experimentlens.models import DesignStatus, Reliability
from experimentlens.reliability import (
    MultipleTestingContext,
    ReliabilityAuditContext,
    StoppingContext,
    audit_reliability,
)


def arm(n: int = 2_000, successes: int = 200, **kwargs: int) -> ArmCounts:
    assignment = kwargs.pop("assignment_count", n)
    eligible = kwargs.pop("eligible_count", assignment)
    success_count = kwargs.pop("success_count", successes)
    categories = sum(kwargs.get(name, 0) for name in (
        "missing_count", "invalid_count", "duplicate_count"
    ))
    excluded = kwargs.pop("excluded_count", categories)
    records = kwargs.pop("records_received", eligible + excluded)
    return ArmCounts(assignment, records, eligible, success_count,
                     excluded_count=excluded, **kwargs)


def audit(**kwargs):
    context = kwargs.pop("context", None)
    config = kwargs.pop("config", AnalysisConfig())
    return audit_reliability(arm(**kwargs.pop("control", {})), arm(**kwargs.pop("treatment", {})),
                             config, context=context, **kwargs)


def test_clean_confirmatory_audit_is_acceptable_and_deterministic():
    first = audit(design_status=DesignStatus.ADEQUATELY_POWERED)
    second = audit(design_status=DesignStatus.ADEQUATELY_POWERED)
    assert first.overall_reliability == Reliability.ACCEPTABLE
    assert first.findings == ()
    assert first.to_dict() == second.to_dict()
    assert first.categories_checked == second.categories_checked


def test_missing_invalid_and_exclusion_controls_are_explicit():
    result = audit(
        control={"missing_count": 1, "invalid_count": 1, "excluded_count": 2},
        treatment={"excluded_count": 200},
    )
    assert result.blocking
    assert "missing_or_invalid_records" in result.reason_codes
    assert "exclusion_rate_exceeded" in result.reason_codes


def test_duplicates_and_cross_group_contamination_block_confirmatory():
    result = audit(
        control={"duplicate_count": 2},
        context=ReliabilityAuditContext(cross_group_count=3),
    )
    assert result.overall_reliability == Reliability.BLOCKED
    assert set(result.reason_codes) >= {"duplicate_assignment", "cross_group_contamination"}


def test_cross_group_contamination_is_review_only_for_exploratory():
    result = audit(context=ReliabilityAuditContext(cross_group_count=1, confirmatory=False))
    assert result.overall_reliability == Reliability.REVIEW_RECOMMENDED
    assert not result.blocking


def test_srm_warning_and_failure_use_assignment_counts():
    warning = audit(
        control={"assignment_count": 100, "records_received": 100, "eligible_count": 100,
                 "success_count": 10},
        treatment={"assignment_count": 130, "records_received": 130, "eligible_count": 130,
                   "success_count": 13},
        design_status=DesignStatus.ADEQUATELY_POWERED,
    )
    assert "srm_warning" in warning.reason_codes
    assert not warning.blocking

    failure = audit(
        control={"assignment_count": 100, "records_received": 100, "eligible_count": 100,
                 "success_count": 10},
        treatment={"assignment_count": 300, "records_received": 300, "eligible_count": 300,
                   "success_count": 30},
        design_status=DesignStatus.ADEQUATELY_POWERED,
    )
    assert "srm_failure" in failure.reason_codes
    assert failure.blocking


def test_power_states_are_distinguished():
    underpowered = audit(design_status=DesignStatus.UNDERPOWERED)
    assert underpowered.reason_codes == ("underpowered",)
    assert underpowered.overall_reliability == Reliability.REVIEW_RECOMMENDED

    unavailable = audit(design_status=DesignStatus.UNAVAILABLE)
    assert unavailable.reason_codes == ("power_unavailable",)
    planning_error = audit(planning_error="MDE is not estimable")
    assert planning_error.reason_codes == ("power_planning_unavailable",)


def test_multiple_testing_policy():
    blocked = audit(context=ReliabilityAuditContext(
        multiple_testing=MultipleTestingContext(hypothesis_count=2, primary_hypothesis_count=2),
    ), design_status=DesignStatus.ADEQUATELY_POWERED)
    assert blocked.reason_codes == ("multiple_primary_hypotheses",)
    assert blocked.blocking

    exploratory = audit(context=ReliabilityAuditContext(
        confirmatory=False,
        multiple_testing=MultipleTestingContext(hypothesis_count=2),
    ), design_status=DesignStatus.ADEQUATELY_POWERED)
    assert exploratory.reason_codes == ("exploratory_multiple_testing",)
    assert exploratory.overall_reliability == Reliability.REVIEW_RECOMMENDED

    adjusted = audit(context=ReliabilityAuditContext(
        multiple_testing=MultipleTestingContext(
            hypothesis_count=2, primary_hypothesis_count=2,
            adjustment_applied=True, adjustment_method="declared",
        ),
    ), design_status=DesignStatus.ADEQUATELY_POWERED)
    assert adjusted.reason_codes == ()


def test_stopping_and_preregistration_policy():
    result = audit(
        context=ReliabilityAuditContext(stopping=StoppingContext(interim_looks=1)),
        design_status=DesignStatus.ADEQUATELY_POWERED,
    )
    assert result.reason_codes == ("unauthorized_interim_look",)
    assert result.blocking

    exploratory = audit(context=ReliabilityAuditContext(
        confirmatory=False,
        stopping=StoppingContext(optional_stopping_declared=True),
    ), design_status=DesignStatus.ADEQUATELY_POWERED)
    assert exploratory.reason_codes == ("optional_stopping_detected",)
    assert not exploratory.blocking

    unsupported = audit(context=ReliabilityAuditContext(
        stopping=StoppingContext(registered_stopping_rule="calendar"),
    ), design_status=DesignStatus.ADEQUATELY_POWERED)
    assert unsupported.reason_codes == ("stopping_rule_not_fixed",)

    missing = audit(
        config=AnalysisConfig(pre_registration_status=PreRegistrationStatus.NOT_REGISTERED),
        design_status=DesignStatus.ADEQUATELY_POWERED,
    )
    assert missing.reason_codes == ("preregistration_missing",)
    assert missing.blocking


def test_invalid_audit_context_values_raise_validation_error():
    with pytest.raises(ValidationError):
        MultipleTestingContext(hypothesis_count=0)
    with pytest.raises(ValidationError):
        StoppingContext(interim_looks=-1)


def test_analysis_contains_typed_audit_fields():
    experiment = BinaryExperimentInput(
        "audit-result",
        arm(),
        arm(),
        audit_context=ReliabilityAuditContext(
            multiple_testing=MultipleTestingContext(hypothesis_count=2),
        ),
    )
    result = analyze(experiment)
    payload = result.to_dict()
    assert payload["reliability_audit"]["overall_reliability"] == "blocked"
    assert payload["audit_reason_codes"] == ["multiple_testing_not_declared"]
