"""Binary effect metrics with explicit precondition validation."""

import math

from .errors import ValidationError


def _rate(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValidationError(f"{name} must be finite")
    if not 0 <= value <= 1:
        raise ValidationError(f"{name} must be in [0, 1]")
    return float(value)

def conversion_rate(successes: int, eligible: int) -> float | None:
    """Return a conversion proportion, undefined for zero eligible units."""
    if isinstance(successes, bool) or not isinstance(successes, int) or successes < 0:
        raise ValidationError("successes must be a non-negative integer")
    if isinstance(eligible, bool) or not isinstance(eligible, int) or eligible < 0:
        raise ValidationError("eligible must be a non-negative integer")
    if successes > eligible:
        raise ValidationError("successes cannot exceed eligible")
    return None if eligible == 0 else successes / eligible

def absolute_lift(control_rate: float, treatment_rate: float) -> float:
    """Return treatment minus control conversion rate."""
    return _rate(treatment_rate, "treatment_rate") - _rate(control_rate, "control_rate")

def relative_lift(control_rate: float, treatment_rate: float) -> float | None:
    """Return descriptive relative lift, undefined at a zero control rate."""
    control = _rate(control_rate, "control_rate")
    treatment = _rate(treatment_rate, "treatment_rate")
    if control == 0:
        return None
    return (treatment - control) / control
