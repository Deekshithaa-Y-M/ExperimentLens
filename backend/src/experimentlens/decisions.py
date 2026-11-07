"""Practical-significance and verdict policy."""

import math

from .errors import ValidationError
from .models import (
    AnalysisConfig,
    AnalysisStatus,
    Direction,
    EvidenceStatus,
    Interval,
    Reliability,
    Verdict,
)


def practical_support(effect: float, interval: Interval, config: AnalysisConfig) -> tuple[bool, bool]:
    """Return point-estimate and confidence-interval support for the MDE."""
    if not isinstance(interval, Interval) or not isinstance(config, AnalysisConfig):
        raise ValidationError("interval and config types are invalid")
    if not math.isfinite(effect):
        raise ValidationError("effect must be finite")
    if interval.lower > interval.upper:
        raise ValidationError("interval lower bound cannot exceed upper bound")
    if config.mde_direction == Direction.HIGHER:
        return effect >= config.absolute_mde, interval.lower >= config.absolute_mde
    if config.mde_direction == Direction.LOWER:
        return effect <= -config.absolute_mde, interval.upper <= -config.absolute_mde
    return (
        abs(effect) >= config.absolute_mde,
        interval.lower >= config.absolute_mde or interval.upper <= -config.absolute_mde,
    )


def verdict_for(
    p_value: float,
    effect: float,
    interval: Interval,
    config: AnalysisConfig,
    exploratory: bool,
    underpowered: bool,
    reliability: Reliability,
) -> tuple[AnalysisStatus, EvidenceStatus, Verdict | None]:
    """Apply significance, direction, MDE, and registration policy."""
    if not isinstance(reliability, Reliability):
        raise ValidationError("reliability is invalid")
    if not math.isfinite(p_value) or not 0 <= p_value <= 1:
        raise ValidationError("p_value must be in [0, 1]")
    if exploratory:
        evidence = EvidenceStatus.SIGNIFICANT if p_value < config.alpha else EvidenceStatus.NON_SIGNIFICANT
        return AnalysisStatus.EXPLORATORY, evidence, None
    if reliability == Reliability.BLOCKED:
        return AnalysisStatus.BLOCKED, EvidenceStatus.UNAVAILABLE, Verdict.CANNOT_ANALYZE
    if p_value >= config.alpha:
        evidence = EvidenceStatus.INSUFFICIENT_EVIDENCE if underpowered else EvidenceStatus.NON_SIGNIFICANT
        return AnalysisStatus.CONFIRMATORY, evidence, Verdict.INCONCLUSIVE

    point, supported = practical_support(effect, interval, config)
    if not point:
        return (
            AnalysisStatus.CONFIRMATORY,
            EvidenceStatus.SIGNIFICANT,
            Verdict.STATISTICALLY_SIGNIFICANT_PRACTICALLY_WEAK,
        )
    if not supported:
        return (
            AnalysisStatus.CONFIRMATORY,
            EvidenceStatus.SIGNIFICANT,
            Verdict.STATISTICALLY_SIGNIFICANT_PRACTICAL_IMPACT_UNCERTAIN,
        )

    if config.mde_direction == Direction.HIGHER:
        favorable = effect > 0
    elif config.mde_direction == Direction.LOWER:
        favorable = effect < 0
    else:
        favorable = effect > 0
    verdict = Verdict.POSITIVE_RESULT if favorable else Verdict.NEGATIVE_RESULT
    return AnalysisStatus.CONFIRMATORY, EvidenceStatus.SIGNIFICANT, verdict
