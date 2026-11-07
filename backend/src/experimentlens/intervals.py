"""Wilson and Newcombe confidence intervals."""

import math
from statistics import NormalDist

from .errors import ValidationError
from .models import Interval


def wilson_interval(successes: int, trials: int, confidence_level: float = 0.95) -> Interval | None:
    """Compute a Wilson score interval for a binomial proportion."""
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 0:
        raise ValidationError("trials must be a non-negative integer")
    if isinstance(successes, bool) or not isinstance(successes, int) or successes < 0:
        raise ValidationError("successes must be a non-negative integer")
    if successes > trials:
        raise ValidationError("successes cannot exceed trials")
    if not isinstance(confidence_level, (int, float)) or not math.isfinite(confidence_level):
        raise ValidationError("confidence_level must be finite")
    if not 0 < confidence_level < 1:
        raise ValidationError("confidence_level must be strictly between 0 and 1")
    if trials == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence_level) / 2)
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    margin = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    lower = 0.0 if successes == 0 else max(0.0, center - margin)
    upper = 1.0 if successes == trials else min(1.0, center + margin)
    return Interval(lower, upper)

def newcombe_interval(control_successes: int, control_trials: int, treatment_successes: int,
                      treatment_trials: int, confidence_level: float = 0.95) -> Interval | None:
    """Compute Newcombe's interval from independent Wilson intervals."""
    if not isinstance(control_trials, int) or not isinstance(treatment_trials, int):
        raise ValidationError("trial counts must be integers")
    control = wilson_interval(control_successes, control_trials, confidence_level)
    treatment = wilson_interval(treatment_successes, treatment_trials, confidence_level)
    if control is None or treatment is None:
        return None
    return Interval(treatment.lower - control.upper, treatment.upper - control.lower)
