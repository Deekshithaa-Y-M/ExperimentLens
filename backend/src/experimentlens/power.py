"""Direction-aware binary power planning and design sufficiency."""

import math
from statistics import NormalDist

from .errors import ValidationError
from .models import AnalysisConfig, DesignStatus, Direction

PAIR_SEARCH_MAX_TOTAL = 2_000_000
ALLOCATION_TOLERANCE_FACTOR = 1

def _validate_baseline(baseline_rate: float) -> None:
    if (isinstance(baseline_rate, bool) or not isinstance(baseline_rate, (int, float))
            or not math.isfinite(baseline_rate) or not 0 <= baseline_rate <= 1):
        raise ValidationError("baseline_rate must be finite and in [0, 1]")


def treatment_rate_at_mde(baseline_rate: float, config: AnalysisConfig) -> float:
    """Return the pre-registered alternative rate without reversing direction."""
    if not isinstance(config, AnalysisConfig):
        raise ValidationError("config must be an AnalysisConfig value")
    _validate_baseline(baseline_rate)
    if config.mde_direction == Direction.LOWER:
        alternative = baseline_rate - config.absolute_mde
    else:
        alternative = baseline_rate + config.absolute_mde
    if not 0 < alternative < 1 or alternative == baseline_rate:
        raise ValidationError("absolute MDE cannot define an interior probability alternative")
    return alternative


def planned_power(control_n: int, treatment_n: int, baseline_rate: float,
                  treatment_rate: float, alpha: float) -> float:
    """Calculate normal-approximation two-sided power for a sample-size pair."""
    if (isinstance(control_n, bool) or not isinstance(control_n, int)
            or isinstance(treatment_n, bool) or not isinstance(treatment_n, int)):
        raise ValidationError("sample sizes must be integers")
    if control_n <= 0 or treatment_n <= 0:
        raise ValidationError("sample sizes must be positive")
    _validate_baseline(baseline_rate)
    _validate_baseline(treatment_rate)
    if not 0 < alpha < 1:
        raise ValidationError("alpha must be strictly between 0 and 1")
    delta = treatment_rate - baseline_rate
    if delta == 0:
        raise ValidationError("treatment rate must differ from baseline")
    se_null = math.sqrt(baseline_rate * (1 - baseline_rate) * (1 / control_n + 1 / treatment_n))
    se_alt = math.sqrt(
        baseline_rate * (1 - baseline_rate) / control_n
        + treatment_rate * (1 - treatment_rate) / treatment_n
    )
    if se_null == 0 or se_alt == 0:
        raise ValidationError("planning variance is zero at a probability boundary")
    critical = NormalDist().inv_cdf(1 - alpha / 2) * se_null
    mean = abs(delta)
    distribution = NormalDist(mean, se_alt)
    return distribution.cdf(-critical) + (1 - distribution.cdf(critical))


def _one_to_one_formula(baseline_rate: float, config: AnalysisConfig,
                        alternative: float) -> int:
    z_alpha = NormalDist().inv_cdf(1 - config.alpha / 2)
    z_power = NormalDist().inv_cdf(config.target_power)
    p_bar = (baseline_rate + alternative) / 2
    numerator = (
        z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
        + z_power * math.sqrt(
            baseline_rate * (1 - baseline_rate) + alternative * (1 - alternative)
        )
    ) ** 2
    return math.ceil(numerator / (alternative - baseline_rate) ** 2)


def required_sample_sizes(baseline_rate: float, config: AnalysisConfig) -> tuple[int, int]:
    """Search integer pairs for target power while preserving expected allocation."""
    if not isinstance(config, AnalysisConfig):
        raise ValidationError("config must be an AnalysisConfig value")
    alternative = treatment_rate_at_mde(baseline_rate, config)
    if config.expected_treatment_share == 0.5:
        n = _one_to_one_formula(baseline_rate, config, alternative)
        while planned_power(n, n, baseline_rate, alternative, config.alpha) < config.target_power:
            n += 1
        return n, n

    max_total = PAIR_SEARCH_MAX_TOTAL
    share = config.expected_treatment_share
    for total in range(2, max_total + 1):
        treatment = round(total * share)
        control = total - treatment
        if control <= 0 or treatment <= 0:
            continue
        observed_share = treatment / total
        if abs(observed_share - share) > ALLOCATION_TOLERANCE_FACTOR / total:
            continue
        if planned_power(control, treatment, baseline_rate, alternative, config.alpha) >= config.target_power:
            return control, treatment
    raise ValidationError("no valid allocation-preserving sample pair within planning search bound")


def design_status(control_n: int, treatment_n: int, required: tuple[int, int]) -> DesignStatus:
    """Classify observed sample sizes against the registered requirements."""
    if not isinstance(required, tuple) or len(required) != 2:
        raise ValidationError("required must contain control and treatment sample sizes")
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0
           for value in (control_n, treatment_n, *required)):
        raise ValidationError("sample sizes must be non-negative integers")
    return (DesignStatus.ADEQUATELY_POWERED
            if control_n >= required[0] and treatment_n >= required[1]
            else DesignStatus.UNDERPOWERED)
