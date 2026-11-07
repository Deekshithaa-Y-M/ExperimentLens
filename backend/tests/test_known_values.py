"""Hand-checkable fixtures for metrics, intervals, tests, and planning."""

import pytest

from experimentlens import AnalysisConfig
from experimentlens.intervals import newcombe_interval, wilson_interval
from experimentlens.metrics import absolute_lift, conversion_rate, relative_lift
from experimentlens.power import planned_power, required_sample_sizes
from experimentlens.tests import two_proportion_test


def test_known_conversion_and_lift_values() -> None:
    assert conversion_rate(25, 100) == pytest.approx(0.25, abs=1e-15)
    assert conversion_rate(30, 100) == pytest.approx(0.30, abs=1e-15)
    assert absolute_lift(0.25, 0.30) == pytest.approx(0.05, abs=1e-15)
    assert relative_lift(0.25, 0.30) == pytest.approx(0.20, abs=1e-15)


def test_known_z_test_fixture() -> None:
    result = two_proportion_test(25, 100, 30, 100)

    assert result.method == "two_proportion_z"
    assert result.statistic == pytest.approx(0.7918075824648956, rel=1e-12, abs=1e-14)
    assert result.p_value == pytest.approx(0.4284728804428174, rel=1e-12, abs=1e-14)


def test_known_fisher_fixture() -> None:
    result = two_proportion_test(0, 4, 1, 4)

    assert result.method == "fisher_exact"
    assert result.p_value == pytest.approx(1.0, abs=1e-15)


def test_known_interval_fixtures() -> None:
    interval = wilson_interval(10, 100)
    difference = newcombe_interval(10, 100, 20, 100)

    assert interval is not None
    assert interval.lower == pytest.approx(0.0552291370606751, rel=1e-12, abs=1e-14)
    assert interval.upper == pytest.approx(0.17436566150491345, rel=1e-12, abs=1e-14)
    assert difference is not None
    assert difference.lower == pytest.approx(-0.04099872817388095, rel=1e-12, abs=1e-14)
    assert difference.upper == pytest.approx(0.23360002853248374, rel=1e-12, abs=1e-14)


def test_known_power_and_sample_size_fixture() -> None:
    power = planned_power(400, 400, 0.20, 0.25, 0.05)
    required = required_sample_sizes(
        0.20,
        AnalysisConfig(absolute_mde=0.05),
    )

    assert power == pytest.approx(0.4270096071720111, rel=1e-12, abs=1e-14)
    assert required == (1094, 1094)
