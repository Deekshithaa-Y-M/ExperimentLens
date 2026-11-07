import math

import pytest
from scipy.stats import fisher_exact

from experimentlens import (
    AnalysisConfig,
    ArmCounts,
    BinaryExperimentInput,
    Direction,
    PreRegistrationStatus,
    analyze,
)
from experimentlens.decisions import practical_support, verdict_for
from experimentlens.errors import ValidationError
from experimentlens.intervals import newcombe_interval, wilson_interval
from experimentlens.metrics import absolute_lift, conversion_rate, relative_lift
from experimentlens.models import Interval, Reliability, Verdict
from experimentlens.power import planned_power, required_sample_sizes, treatment_rate_at_mde
from experimentlens.tests import two_proportion_test
from experimentlens.validation import calculate_srm, exclusion_rate


def arm(n=100, x=10, **kwargs):
    return ArmCounts(n, kwargs.pop("records_received", n), n, x, **kwargs)

def test_model_rejects_invalid_values():
    with pytest.raises(ValidationError):
        ArmCounts(10, 10, 10, 11)
    with pytest.raises(ValidationError):
        AnalysisConfig(alpha=0)
    with pytest.raises(ValidationError):
        AnalysisConfig(expected_treatment_share=math.nan)
    with pytest.raises(ValidationError):
        AnalysisConfig(absolute_mde=0)
    with pytest.raises(ValidationError):
        ArmCounts(10.5, 10, 10, 1)
    with pytest.raises(ValidationError):
        ArmCounts(10, 6, 5, 1, excluded_count=1, valid_count=6)
    with pytest.raises(ValidationError):
        ArmCounts(10, 5, 5, 1, missing_count=1, excluded_count=0)


def test_count_categories_and_direction_metadata_are_explicit():
    counts = ArmCounts(10, 12, 8, 2, missing_count=1, invalid_count=1,
                       duplicate_count=1, excluded_count=3, valid_count=8)
    assert counts.valid_count == 8
    config = AnalysisConfig(metric_direction=Direction.LOWER, mde_direction=Direction.HIGHER)
    result = analyze(BinaryExperimentInput("metadata", arm(), arm(), config))
    payload = result.to_dict()
    assert result.metric_direction == Direction.LOWER
    assert result.mde_direction == Direction.HIGHER
    assert payload["metric_direction"] == "lower"
    assert payload["mde_direction"] == "higher"
    assert payload["mde_value"] == config.absolute_mde
    assert payload["control_label"] == "control"
    assert payload["randomization_unit"] == "randomization_unit"

def test_metrics_and_intervals():
    assert conversion_rate(0, 10) == 0
    assert conversion_rate(0, 0) is None
    assert conversion_rate(10, 10) == 1
    assert absolute_lift(.2, .3) == pytest.approx(.1)
    assert relative_lift(0, .3) is None
    assert relative_lift(.2, .3) == pytest.approx(.5)
    interval = wilson_interval(10, 100)
    assert interval and 0 <= interval.lower <= interval.upper <= 1
    difference = newcombe_interval(10, 100, 20, 100)
    assert difference and difference.lower <= difference.upper
    zero = wilson_interval(0, 10)
    full = wilson_interval(10, 10)
    assert zero and zero.lower == 0
    assert full and full.upper == 1
    assert wilson_interval(1, 5, .90).lower <= wilson_interval(1, 5, .90).upper
    assert newcombe_interval(0, 10, 0, 10)
    assert newcombe_interval(10, 10, 10, 10)
    with pytest.raises(ValidationError):
        wilson_interval(1, 1, 1.0)

def test_method_selection_matches_scipy():
    result = two_proportion_test(10, 100, 20, 100)
    assert result.method == "two_proportion_z"
    sparse = two_proportion_test(0, 4, 1, 4)
    assert sparse.method == "fisher_exact"
    assert sparse.p_value == pytest.approx(fisher_exact([[0, 4], [1, 3]])[1])
    assert two_proportion_test(0, 100, 0, 100).statistic is None

def test_srm_uses_assignments_not_eligible_counts():
    result = calculate_srm(ArmCounts(100, 10, 10, 1), ArmCounts(120, 10, 10, 1), .5)
    assert result and result.observed_share == pytest.approx(120 / 220)
    assert exclusion_rate(ArmCounts(10, 0, 0, 0)) is None

def test_analysis_complete_result_and_reproducibility():
    result = analyze(BinaryExperimentInput("experiment-1", arm(100, 10), arm(100, 20)))
    assert result.selected_method == "two_proportion_z"
    assert result.specification_version == "1.0"
    assert result.reproducibility["random_seed"] is None
    assert result.to_dict() == analyze(BinaryExperimentInput("experiment-1", arm(100, 10), arm(100, 20))).to_dict()

def test_blocking_quality_overrides_significance_and_zero_eligible_is_undefined():
    blocked = analyze(BinaryExperimentInput(
        "bad", arm(100, 100, records_received=101, duplicate_count=1, excluded_count=1), arm(100, 0)
    ))
    assert blocked.verdict.value == "cannot_analyze"
    assert blocked.analysis_status.value == "blocked"
    assert blocked.control_rate is None or blocked.treatment_rate == 0
    assert blocked.reliability.value == "blocked"

def test_exploratory_has_no_verdict():
    config = AnalysisConfig(pre_registration_status=PreRegistrationStatus.NOT_REGISTERED)
    result = analyze(BinaryExperimentInput("explore", arm(100, 10), arm(100, 30), config))
    assert result.analysis_status.value == "exploratory"
    assert result.verdict is None


def test_direction_aware_decisions_and_boundaries():
    higher = AnalysisConfig(mde_direction=Direction.HIGHER)
    lower = AnalysisConfig(mde_direction=Direction.LOWER)
    either = AnalysisConfig(mde_direction=Direction.EITHER)
    positive = Interval(.06, .20)
    negative = Interval(-.20, -.06)
    assert practical_support(.10, positive, higher) == (True, True)
    assert practical_support(-.10, negative, lower) == (True, True)
    assert verdict_for(.01, .10, positive, higher, False, False, Reliability.ACCEPTABLE)[2] == Verdict.POSITIVE_RESULT
    assert verdict_for(.01, -.10, negative, either, False, False, Reliability.ACCEPTABLE)[2] == Verdict.NEGATIVE_RESULT
    assert verdict_for(.01, -.10, negative, higher, False, False, Reliability.ACCEPTABLE)[2] != Verdict.POSITIVE_RESULT
    assert verdict_for(.01, .10, positive, lower, False, False, Reliability.ACCEPTABLE)[2] != Verdict.NEGATIVE_RESULT
    assert verdict_for(.05, .10, positive, higher, False, False, Reliability.ACCEPTABLE)[2] == Verdict.INCONCLUSIVE
    assert practical_support(.05, positive, higher)[0]


def test_power_is_direction_aware_and_non_equal_allocation_is_searched():
    higher = AnalysisConfig(absolute_mde=.05, mde_direction=Direction.HIGHER)
    lower = AnalysisConfig(absolute_mde=.05, mde_direction=Direction.LOWER)
    assert treatment_rate_at_mde(.2, higher) == pytest.approx(.25)
    assert treatment_rate_at_mde(.2, lower) == pytest.approx(.15)
    with pytest.raises(ValidationError):
        treatment_rate_at_mde(.99, higher)
    config = AnalysisConfig(expected_treatment_share=.6, absolute_mde=.1)
    control, treatment = required_sample_sizes(.2, config)
    assert planned_power(control, treatment, .2, .3, config.alpha) >= config.target_power
    assert abs(treatment / (control + treatment) - .6) <= 1 / (control + treatment)
    assert "search_max_total" in analyze(
        BinaryExperimentInput("power-meta", arm(), arm(), config)
    ).planning_metadata


def test_planning_unavailable_does_not_block_estimable_statistics():
    config = AnalysisConfig(absolute_mde=.1, mde_direction=Direction.LOWER)
    result = analyze(BinaryExperimentInput("no-plan", arm(4, 0), arm(4, 1), config))
    assert result.control_rate == 0
    assert result.selected_method == "fisher_exact"
    assert result.required_control_sample_size is None
    assert result.required_treatment_sample_size is None
    assert result.design_status.value == "unavailable"
    assert result.analysis_status.value == "confirmatory"
    assert result.verdict != Verdict.CANNOT_ANALYZE
