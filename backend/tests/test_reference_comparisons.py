"""Independent reference comparisons for the Phase 3 statistical core."""

import math

import pytest
from scipy.stats import fisher_exact, norm

from experimentlens.intervals import newcombe_interval, wilson_interval
from experimentlens.power import planned_power
from experimentlens.tests import two_proportion_test


def _reference_wilson(successes: int, trials: int, confidence: float) -> tuple[float, float]:
    z = norm.ppf(1 - (1 - confidence) / 2)
    p = successes / trials
    scale = 1 + z**2 / trials
    center = (p + z**2 / (2 * trials)) / scale
    margin = z * math.sqrt(p * (1 - p) / trials + z**2 / (4 * trials**2)) / scale
    return max(0.0, center - margin), min(1.0, center + margin)


def test_z_test_matches_independent_normal_reference() -> None:
    successes_control, trials_control = 42, 500
    successes_treatment, trials_treatment = 61, 480
    pooled = (successes_control + successes_treatment) / (trials_control + trials_treatment)
    se = math.sqrt(
        pooled * (1 - pooled) * (1 / trials_control + 1 / trials_treatment)
    )
    z_reference = (
        successes_treatment / trials_treatment - successes_control / trials_control
    ) / se
    p_reference = 2 * norm.sf(abs(z_reference))

    result = two_proportion_test(
        successes_control, trials_control, successes_treatment, trials_treatment
    )

    assert result.method == "two_proportion_z"
    assert result.statistic == pytest.approx(z_reference, rel=1e-12, abs=1e-14)
    assert result.p_value == pytest.approx(p_reference, rel=1e-12, abs=1e-14)


def test_fisher_matches_scipy_exact_reference() -> None:
    table = [[1, 9], [6, 4]]
    expected = fisher_exact(table, alternative="two-sided").pvalue

    result = two_proportion_test(1, 10, 6, 10)

    assert result.method == "fisher_exact"
    assert result.p_value == pytest.approx(expected, rel=1e-14, abs=1e-15)


@pytest.mark.parametrize(
    ("successes", "trials", "confidence"),
    [(10, 100, 0.95), (0, 12, 0.95), (12, 12, 0.95), (1, 5, 0.90)],
)
def test_wilson_matches_independent_reference(
    successes: int, trials: int, confidence: float
) -> None:
    expected = _reference_wilson(successes, trials, confidence)
    actual = wilson_interval(successes, trials, confidence)

    assert actual is not None
    assert actual.lower == pytest.approx(expected[0], rel=1e-12, abs=1e-14)
    assert actual.upper == pytest.approx(expected[1], rel=1e-12, abs=1e-14)


def test_newcombe_matches_difference_of_independent_reference_intervals() -> None:
    control = _reference_wilson(20, 200, 0.95)
    treatment = _reference_wilson(35, 200, 0.95)
    expected = (treatment[0] - control[1], treatment[1] - control[0])

    actual = newcombe_interval(20, 200, 35, 200)

    assert actual is not None
    assert actual.lower == pytest.approx(expected[0], rel=1e-12, abs=1e-14)
    assert actual.upper == pytest.approx(expected[1], rel=1e-12, abs=1e-14)


def test_planned_power_matches_independent_normal_cdf_reference() -> None:
    control_n, treatment_n = 400, 450
    baseline, treatment, alpha = 0.20, 0.27, 0.05
    null_se = math.sqrt(baseline * (1 - baseline) * (1 / control_n + 1 / treatment_n))
    alternative_se = math.sqrt(
        baseline * (1 - baseline) / control_n
        + treatment * (1 - treatment) / treatment_n
    )
    critical = norm.ppf(1 - alpha / 2) * null_se
    mean = abs(treatment - baseline)
    expected = norm.cdf((-critical - mean) / alternative_se) + norm.sf(
        (critical - mean) / alternative_se
    )

    assert planned_power(control_n, treatment_n, baseline, treatment, alpha) == pytest.approx(
        expected, rel=1e-12, abs=1e-14
    )
