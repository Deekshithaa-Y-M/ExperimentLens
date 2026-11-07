"""Two-proportion test selection and execution."""

import math
from dataclasses import dataclass

import numpy as np
from scipy.stats import fisher_exact, norm

from .errors import ValidationError


@dataclass(frozen=True)
class TestResult:
    method: str
    reason: str
    statistic: float | None
    p_value: float
    degrees_of_freedom: int | None

def expected_cells(control_successes: int, control_trials: int, treatment_successes: int,
                   treatment_trials: int) -> tuple[float, float, float, float]:
    """Return expected success/failure cells under equal rates."""
    values = (control_successes, control_trials, treatment_successes, treatment_trials)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValidationError("test counts must be non-negative integers")
    if control_trials == 0 or treatment_trials == 0:
        raise ValidationError("test trials must be positive")
    if control_successes > control_trials or treatment_successes > treatment_trials:
        raise ValidationError("successes cannot exceed trials")
    total = control_trials + treatment_trials
    pooled = (control_successes + treatment_successes) / total
    return (control_trials * pooled, control_trials * (1 - pooled),
            treatment_trials * pooled, treatment_trials * (1 - pooled))

def two_proportion_test(control_successes: int, control_trials: int, treatment_successes: int,
                        treatment_trials: int) -> TestResult:
    """Select the specified z-test or exact Fisher test and calculate its result."""
    expected = expected_cells(control_successes, control_trials, treatment_successes, treatment_trials)
    pooled = (control_successes + treatment_successes) / (control_trials + treatment_trials)
    se = math.sqrt(pooled * (1 - pooled) * (1 / control_trials + 1 / treatment_trials))
    sparse = min(expected) < 5
    if sparse or se == 0:
        table = np.array(
            [
                [control_successes, control_trials - control_successes],
                [treatment_successes, treatment_trials - treatment_successes],
            ]
        )
        _, p_value = fisher_exact(table, alternative="two-sided")
        reason = "expected cell below 5" if sparse else "z-test standard error is zero"
        return TestResult("fisher_exact", reason, None, float(p_value), None)
    z = ((treatment_successes / treatment_trials) - (control_successes / control_trials)) / se
    p_value = 2 * norm.sf(abs(z))
    return TestResult("two_proportion_z", "all expected cells are at least 5",
                      float(z), float(p_value), None)
