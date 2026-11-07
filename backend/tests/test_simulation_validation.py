"""Reproducible Monte Carlo checks with explicit acceptance thresholds."""

import numpy as np

from experimentlens import AnalysisConfig, ArmCounts, BinaryExperimentInput, analyze
from experimentlens.intervals import wilson_interval
from experimentlens.tests import two_proportion_test
from experimentlens.validation import calculate_srm


def _replicate(seed: int, replications: int = 2000) -> dict[str, int | float]:
    rng = np.random.default_rng(seed)
    significant = 0
    covered = 0
    srm_detected = 0
    for _ in range(replications):
        control = int(rng.binomial(200, 0.20))
        treatment = int(rng.binomial(200, 0.20))
        result = two_proportion_test(control, 200, treatment, 200)
        significant += result.p_value < 0.05
        interval = wilson_interval(control, 200)
        if interval is not None and interval.lower <= 0.20 <= interval.upper:
            covered += 1
        srm = calculate_srm(ArmCounts(200, 200, 200, control), ArmCounts(200, 200, 200, treatment), 0.5)
        if srm is not None:
            srm_detected += srm.p_value < 0.001
    return {
        "significant": significant,
        "covered": covered,
        "srm_detected": srm_detected,
        "replications": replications,
    }


def test_null_false_positive_and_interval_coverage_are_reproducible() -> None:
    first = _replicate(20261031)
    second = _replicate(20261031)

    assert first == second
    false_positive = first["significant"] / first["replications"]
    coverage = first["covered"] / first["replications"]
    assert 0.02 <= false_positive <= 0.08
    assert 0.90 <= coverage <= 0.99
    assert first["srm_detected"] == 0


def test_power_under_known_effect_and_srm_detection() -> None:
    rng = np.random.default_rng(20261101)
    replications = 2000
    significant = 0
    srm_detected = 0
    for _ in range(replications):
        control = int(rng.binomial(200, 0.20))
        treatment = int(rng.binomial(200, 0.30))
        result = two_proportion_test(control, 200, treatment, 200)
        significant += result.p_value < 0.05
        srm = calculate_srm(ArmCounts(200, 200, 200, control), ArmCounts(300, 300, 300, treatment), 0.5)
        if srm is not None:
            srm_detected += srm.p_value < 0.001

    power = significant / replications
    detection = srm_detected / replications
    assert 0.45 <= power <= 0.75
    assert detection >= 0.95


def test_sparse_and_degenerate_simulation_is_deterministic() -> None:
    rng = np.random.default_rng(20261102)
    outcomes = []
    for _ in range(500):
        control = int(rng.binomial(20, 0.01))
        treatment = int(rng.binomial(20, 0.01))
        result = analyze(BinaryExperimentInput(
            "sparse-simulation",
            ArmCounts(20, 20, 20, control),
            ArmCounts(20, 20, 20, treatment),
            AnalysisConfig(),
        ))
        outcomes.append((result.selected_method, result.p_value is not None))

    assert all(method == "fisher_exact" for method, _ in outcomes)
    assert all(has_p_value for _, has_p_value in outcomes)
