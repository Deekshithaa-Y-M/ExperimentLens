"""Application service orchestration for ExperimentLens analyses."""

from dataclasses import dataclass

from .analysis import analyze
from .errors import ValidationError
from .models import AnalysisResult, BinaryExperimentInput, Verdict


@dataclass(frozen=True)
class ServiceResult:
    """A domain result plus stable machine-readable explanation codes."""

    analysis: AnalysisResult
    reason_codes: tuple[str, ...]


class AnalysisService:
    """Run the verified statistical workflow without reimplementing its formulas."""

    def analyze(self, experiment: BinaryExperimentInput) -> ServiceResult:
        if not isinstance(experiment, BinaryExperimentInput):
            raise ValidationError("experiment must be a BinaryExperimentInput")
        result = analyze(experiment)
        codes: list[str] = []
        warning_codes = {warning.code for warning in result.warnings}
        codes.extend(sorted(warning_codes))
        codes.extend(result.audit_reason_codes)
        if result.reasons:
            codes.append("metric_not_estimable")
        if result.analysis_status.value == "blocked":
            codes.append("data_quality_blocked")
        elif result.analysis_status.value == "exploratory":
            codes.append("exploratory_interpretation")
        else:
            codes.append("confirmatory_interpretation")
        if result.evidence_status.value == "significant":
            codes.append("statistically_significant")
        elif result.evidence_status.value == "non_significant":
            codes.append("not_statistically_significant")
        elif result.evidence_status.value == "insufficient_evidence":
            codes.append("insufficient_evidence")
        if result.design_status.value == "underpowered":
            codes.append("underpowered")
        elif result.design_status.value == "adequately_powered":
            codes.append("adequately_powered")
        if result.selected_method:
            codes.append(f"method_{result.selected_method}")
        if result.verdict == Verdict.CANNOT_ANALYZE:
            codes.append("cannot_analyze")
        return ServiceResult(result, tuple(dict.fromkeys(codes)))


def analyze_experiment(experiment: BinaryExperimentInput) -> ServiceResult:
    """Convenience entry point for consumers that do not need a service instance."""
    return AnalysisService().analyze(experiment)
