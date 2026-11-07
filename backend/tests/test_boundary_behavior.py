"""Contract boundary, sparse-table, direction, rounding, and precedence checks."""

import pytest

from experimentlens import AnalysisConfig, ArmCounts, BinaryExperimentInput, Direction, analyze
from experimentlens.decisions import practical_support, verdict_for
from experimentlens.models import AnalysisStatus, Interval, Reliability, Verdict
from experimentlens.power import required_sample_sizes


def arm(n: int, x: int, **kwargs: int) -> ArmCounts:
    return ArmCounts(n, kwargs.pop("records_received", n), n, x, **kwargs)


@pytest.mark.parametrize(
    ("control", "treatment"),
    [(arm(10, 0), arm(10, 1)), (arm(10, 10), arm(10, 9)), (arm(10, 0), arm(10, 0)),
     (arm(10, 10), arm(10, 10)), (arm(1, 0), arm(1, 1))],
)
def test_sparse_and_degenerate_tables_use_exact_test(
    control: ArmCounts, treatment: ArmCounts
) -> None:
    result = analyze(BinaryExperimentInput("sparse", control, treatment))

    assert result.selected_method == "fisher_exact"
    assert result.p_value is not None
    assert result.control_interval is not None
    assert result.treatment_interval is not None
    assert result.difference_interval is not None


def test_zero_eligible_is_undefined_and_blocked() -> None:
    result = analyze(BinaryExperimentInput("empty", arm(0, 0), arm(10, 1)))

    assert result.control_rate is None
    assert result.analysis_status == AnalysisStatus.BLOCKED
    assert result.verdict == Verdict.CANNOT_ANALYZE


@pytest.mark.parametrize(
    ("direction", "effect", "interval", "expected"),
    [
        (Direction.HIGHER, 0.05, Interval(0.05, 0.10), (True, True)),
        (Direction.LOWER, -0.05, Interval(-0.10, -0.05), (True, True)),
        (Direction.EITHER, -0.05, Interval(-0.10, -0.05), (True, True)),
        (Direction.HIGHER, 0.049999999, Interval(0.05, 0.10), (False, True)),
    ],
)
def test_mde_equality_and_direction_boundaries(
    direction: Direction, effect: float, interval: Interval, expected: tuple[bool, bool]
) -> None:
    config = AnalysisConfig(absolute_mde=0.05, mde_direction=direction)
    assert practical_support(effect, interval, config) == expected


@pytest.mark.parametrize("p_value", [0.05, 0.0500000001, 0.0499999999])
def test_alpha_boundary_uses_strictly_less_than(p_value: float) -> None:
    status, evidence, verdict = verdict_for(
        p_value, 0.10, Interval(0.06, 0.20), AnalysisConfig(), False, False,
        Reliability.ACCEPTABLE,
    )

    if p_value < 0.05:
        assert verdict == Verdict.POSITIVE_RESULT
        assert evidence.value == "significant"
    else:
        assert status == AnalysisStatus.CONFIRMATORY
        assert verdict == Verdict.INCONCLUSIVE


def test_data_quality_precedes_significance_and_srm() -> None:
    config = AnalysisConfig(srm_blocking_p_value=0.99)
    result = analyze(BinaryExperimentInput(
        "blocked-significant",
        arm(100, 1, records_received=101, duplicate_count=1, excluded_count=1),
        arm(100, 80),
        config,
    ))

    assert result.p_value is not None and result.p_value < config.alpha
    assert result.analysis_status == AnalysisStatus.BLOCKED
    assert result.reliability == Reliability.BLOCKED
    assert result.verdict == Verdict.CANNOT_ANALYZE


def test_display_rounding_does_not_change_decision_inputs() -> None:
    config = AnalysisConfig(absolute_mde=0.05, mde_direction=Direction.HIGHER)
    effect = 0.0496
    interval = Interval(0.0496, 0.0601)
    assert round(effect, 2) == 0.05
    assert practical_support(effect, interval, config) == (False, False)

    p_value = 0.0504
    assert round(p_value, 2) == 0.05
    assert verdict_for(
        p_value, 0.10, Interval(0.06, 0.20), config, False, False, Reliability.ACCEPTABLE
    )[2] == Verdict.INCONCLUSIVE


def test_non_one_to_one_search_meets_power_and_ratio() -> None:
    config = AnalysisConfig(expected_treatment_share=0.6, absolute_mde=0.10)
    control, treatment = required_sample_sizes(0.20, config)

    assert control > 0 and treatment > 0
    assert abs(treatment / (control + treatment) - 0.6) <= 1 / (control + treatment)
