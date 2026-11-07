"""Versioned FastAPI boundary for the ExperimentLens statistical service."""

import logging
import math
import time
from typing import Any, Literal, cast
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from . import __version__
from .compat import StrEnum
from .errors import ValidationError
from .models import (
    AnalysisConfig,
    ArmCounts,
    BinaryExperimentInput,
    Direction,
    Interval,
    PreRegistrationStatus,
    Warning,
)
from .monitoring import metrics
from .reliability import (
    AuditCategory,
    AuditSeverity,
    MultipleTestingContext,
    ReliabilityAuditContext,
    StoppingContext,
)
from .service import analyze_experiment

logger = logging.getLogger("experimentlens.api")


class AnalysisMode(StrEnum):
    CONFIRMATORY = "confirmatory"
    EXPLORATORY = "exploratory"


class ArmRequest(BaseModel):
    """Strict request representation of one experiment arm."""

    model_config = ConfigDict(extra="forbid")

    assignment_count: StrictInt = Field(ge=0)
    records_received: StrictInt = Field(ge=0)
    eligible_count: StrictInt = Field(ge=0)
    success_count: StrictInt = Field(ge=0)
    missing_count: StrictInt = Field(default=0, ge=0)
    invalid_count: StrictInt = Field(default=0, ge=0)
    excluded_count: StrictInt = Field(default=0, ge=0)
    duplicate_count: StrictInt = Field(default=0, ge=0)
    valid_count: StrictInt | None = Field(default=None, ge=0)


class ConfigRequest(BaseModel):
    """Strict request representation of the pre-registered analysis plan."""

    model_config = ConfigDict(extra="forbid")

    mode: AnalysisMode = AnalysisMode.CONFIRMATORY
    alpha: float = Field(default=0.05, gt=0, lt=1)
    confidence_level: float = Field(default=0.95, gt=0, lt=1)
    target_power: float = Field(default=0.80, gt=0, lt=1)
    expected_treatment_share: float = Field(default=0.50, gt=0, lt=1)
    mde_type: Literal["absolute"] = "absolute"
    mde_value: float = Field(default=0.05, gt=0)
    metric_direction: Direction = Direction.HIGHER
    mde_direction: Direction = Direction.EITHER
    exclusion_tolerance: float = Field(default=0.05, ge=0, lt=1)
    missingness_difference_tolerance: float = Field(default=0.05, ge=0, lt=1)
    srm_warning_threshold: float = Field(default=0.05, ge=0, lt=1)
    srm_blocking_p_value: float = Field(default=0.001, ge=0, lt=1)
    pre_registered: bool | None = None
    hypothesis_count: StrictInt = Field(default=1, gt=0)
    primary_hypothesis_count: StrictInt = Field(default=1, gt=0)
    primary_metric_prespecified: bool = True
    multiplicity_adjustment_applied: bool = False
    multiplicity_adjustment_method: str | None = None
    registered_stopping_rule: str = "fixed"
    interim_looks: StrictInt = Field(default=0, ge=0)
    analysis_before_end_condition: bool = False
    optional_stopping_declared: bool = False
    registered_before_outcome_inspection: bool = True
    cross_group_count: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_finite_values(self) -> "ConfigRequest":
        for name in (
            "alpha",
            "confidence_level",
            "target_power",
            "expected_treatment_share",
            "mde_value",
            "exclusion_tolerance",
            "missingness_difference_tolerance",
            "srm_warning_threshold",
            "srm_blocking_p_value",
        ):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        return self


class AnalysisRequest(BaseModel):
    """JSON request contract for ``POST /api/v1/analyses``."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str = Field(min_length=1)
    control: ArmRequest
    treatment: ArmRequest
    config: ConfigRequest = Field(default_factory=ConfigRequest)

    @model_validator(mode="after")
    def validate_experiment_id(self) -> "AnalysisRequest":
        if not self.experiment_id.strip():
            raise ValueError("experiment_id is required")
        return self


class AnalysisPayload(BaseModel):
    """Typed representation of the full-precision domain result."""

    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    metric_name: str
    metric_type: str
    metric_unit: str
    metric_direction: Direction
    mde_direction: Direction
    primary_or_secondary: str
    mde_type: str
    absolute_mde: float | None
    mde_value: float | None
    control_label: str
    treatment_label: str
    randomization_unit: str
    specification_version: str
    selected_method: str | None
    method_selection_reason: str | None
    control_counts: ArmCounts | None
    treatment_counts: ArmCounts | None
    expected_treatment_share: float | None
    observed_treatment_share: float | None
    allocation_deviation: float | None
    srm_statistic: float | None
    srm_p_value: float | None
    control_rate: float | None
    treatment_rate: float | None
    absolute_lift: float | None
    relative_lift: float | None
    control_interval: Interval | None
    treatment_interval: Interval | None
    difference_interval: Interval | None
    test_statistic: float | None
    degrees_of_freedom: int | None
    p_value: float | None
    alpha: float | None
    confidence_level: float | None
    planned_power: float | None
    required_control_sample_size: int | None
    required_treatment_sample_size: int | None
    design_status: str
    evidence_status: str
    analysis_status: str
    reliability: str
    verdict: str | None
    warnings: list[Warning]
    exclusion_rates: dict[str, float | None]
    records_received: dict[str, int]
    eligible_counts: dict[str, int]
    valid_counts: dict[str, int]
    excluded_counts: dict[str, int]
    missing_counts: dict[str, int]
    invalid_counts: dict[str, int]
    duplicate_counts: dict[str, int]
    exclusion_reasons: dict[str, dict[str, int]]
    pre_registration_status: str | None
    stopping_rule_status: str | None
    reasons: list[str]
    planning_method: str | None
    planning_metadata: dict[str, Any]
    reproducibility: dict[str, Any]
    reliability_audit: "ReliabilityAuditPayload | None"
    audit_findings: list["AuditFindingPayload"]
    audit_reason_codes: list[str]


class AuditFindingPayload(BaseModel):
    code: str
    category: AuditCategory
    severity: AuditSeverity
    message: str
    evidence: str
    remediation: str
    blocking: bool


class ReliabilityAuditPayload(BaseModel):
    findings: list[AuditFindingPayload]
    overall_reliability: str
    blocking: bool
    review_recommended: bool
    categories_checked: list[AuditCategory]
    summary: str
    metadata: dict[str, Any]
    reason_codes: list[str]


AnalysisPayload.model_rebuild()


class AnalysisResponse(BaseModel):
    """Stable response envelope with full-precision analysis data."""

    model_config = ConfigDict(extra="allow")

    experiment_id: str
    analysis: AnalysisPayload
    reason_codes: list[str]


class ErrorDetail(BaseModel):
    location: list[str | int]
    message: str
    type: str


class ErrorResponse(BaseModel):
    error: dict[str, Any]


def _arm(value: ArmRequest) -> ArmCounts:
    return ArmCounts(**value.model_dump())


def _domain_input(value: AnalysisRequest) -> BinaryExperimentInput:
    config = value.config
    confirmatory = config.mode == AnalysisMode.CONFIRMATORY
    return BinaryExperimentInput(
        experiment_id=value.experiment_id,
        control=_arm(value.control),
        treatment=_arm(value.treatment),
        config=AnalysisConfig(
            alpha=config.alpha,
            confidence_level=config.confidence_level,
            target_power=config.target_power,
            expected_treatment_share=config.expected_treatment_share,
            absolute_mde=config.mde_value,
            metric_direction=config.metric_direction,
            mde_direction=config.mde_direction,
            exclusion_tolerance=config.exclusion_tolerance,
            missingness_difference_tolerance=config.missingness_difference_tolerance,
            srm_warning_threshold=config.srm_warning_threshold,
            srm_blocking_p_value=config.srm_blocking_p_value,
            pre_registration_status=(
                PreRegistrationStatus.REGISTERED
                if confirmatory and config.pre_registered is not False
                else PreRegistrationStatus.NOT_REGISTERED
            ),
        ),
        audit_context=ReliabilityAuditContext(
            multiple_testing=MultipleTestingContext(
                hypothesis_count=config.hypothesis_count,
                primary_hypothesis_count=config.primary_hypothesis_count,
                primary_metric_prespecified=config.primary_metric_prespecified,
                adjustment_applied=config.multiplicity_adjustment_applied,
                adjustment_method=config.multiplicity_adjustment_method,
            ),
            stopping=StoppingContext(
                registered_stopping_rule=config.registered_stopping_rule,
                interim_looks=config.interim_looks,
                analysis_before_end_condition=config.analysis_before_end_condition,
                optional_stopping_declared=config.optional_stopping_declared,
                registered_before_outcome_inspection=config.registered_before_outcome_inspection,
            ),
            cross_group_count=config.cross_group_count,
            confirmatory=confirmatory,
        ),
    )


def _finite(value: Any, path: str = "analysis") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{path} contains a non-finite value")
    if isinstance(value, dict):
        for key, child in value.items():
            _finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _finite(child, f"{path}[{index}]")


app = FastAPI(title="ExperimentLens API", version=__version__)


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "")
    if supplied and len(supplied) <= 64 and all(
        character.isalnum() or character in "._-" for character in supplied
    ):
        return supplied
    return uuid4().hex


@app.middleware("http")
async def observability_middleware(request: Request, call_next: Any) -> JSONResponse:
    request_id = _request_id(request)
    request.state.request_id = request_id
    started = time.perf_counter()
    logger.info(
        "request_started",
        extra={"request_id": request_id, "method": request.method, "path": request.url.path},
    )
    try:
        response = await call_next(request)
    except Exception:
        logger.error(
            "request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "error": "internal_error",
            },
        )
        metrics.record_request("internal_error", (time.perf_counter() - started) * 1000)
        raise
    outcome = "success" if response.status_code < 400 else "failure"
    metrics.record_request(outcome, (time.perf_counter() - started) * 1000)
    logger.info(
        "request_completed",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        },
    )
    return cast(JSONResponse, response)


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    metrics.record_request("invalid", 0.0)
    details = [
        {"location": [str(item) for item in error["loc"]], "message": error["msg"],
         "type": error["type"]}
        for error in exc.errors()
    ]
    logger.warning(
        "request_validation_failed",
        extra={"request_id": request.state.request_id, "detail_count": len(details)},
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_analysis_request", "message": "Request validation failed",
                            "details": details}},
    )


@app.exception_handler(ValidationError)
async def domain_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    metrics.record_request("invalid", 0.0)
    logger.warning(
        "domain_validation_failed",
        extra={"request_id": request.state.request_id, "error": str(exc)},
    )
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_analysis_request", "message": str(exc), "details": []}},
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    logger.error(
        "internal_error",
        extra={"request_id": request.state.request_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_analysis_error",
                "message": "The analysis could not be completed.",
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
def readiness() -> dict[str, str]:
    """Report process readiness without implying experiment validity."""
    return {"status": "ready"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"name": "experimentlens", "version": __version__}


@app.get("/metrics")
def metrics_snapshot() -> dict[str, Any]:
    """Return safe process-local aggregates; no request payloads are retained."""
    return metrics.snapshot()


@app.post("/api/v1/analyses", response_model=AnalysisResponse, status_code=200)
def create_analysis(request: AnalysisRequest, http_request: Request) -> AnalysisResponse:
    service_result = analyze_experiment(_domain_input(request))
    payload = service_result.analysis.to_dict()
    _finite(payload)
    response = AnalysisResponse(
        experiment_id=service_result.analysis.experiment_id,
        analysis=AnalysisPayload.model_validate(payload),
        reason_codes=list(service_result.reason_codes),
    )
    if response.analysis.analysis_status == "blocked":
        metrics.record_analysis(
            analysis_status="blocked",
            evidence_status=response.analysis.evidence_status,
            method=response.analysis.selected_method,
            warning_codes=tuple(warning.code for warning in response.analysis.warnings),
        )
        logger.warning(
            "analysis_blocked",
            extra={
                "request_id": http_request.state.request_id,
                "reason_code_count": len(response.reason_codes),
            },
        )
    else:
        metrics.record_analysis(
            analysis_status=response.analysis.analysis_status,
            evidence_status=response.analysis.evidence_status,
            method=response.analysis.selected_method,
            warning_codes=tuple(warning.code for warning in response.analysis.warnings),
        )
        logger.info(
            "analysis_completed",
            extra={
                "request_id": http_request.state.request_id,
                "analysis_status": response.analysis.analysis_status,
                "evidence_status": response.analysis.evidence_status,
            },
        )
    return response
