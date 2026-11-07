"""ExperimentLens Version 1 statistical core."""

__version__ = "0.1.0"

from .analysis import analyze
from .dataset_models import (
    ArmSummary,
    DatasetConfig,
    DatasetIssue,
    DatasetSchema,
    DatasetSummary,
    IngestionResult,
    IssueSeverity,
)
from .ingestion import ingest_csv
from .models import (
    AnalysisConfig,
    AnalysisResult,
    ArmCounts,
    BinaryExperimentInput,
    Direction,
    PreRegistrationStatus,
    WarningSeverity,
)
from .service import AnalysisService, ServiceResult, analyze_experiment

__all__ = [
    "AnalysisConfig",
    "AnalysisResult",
    "AnalysisService",
    "ArmCounts",
    "ArmSummary",
    "BinaryExperimentInput",
    "DatasetConfig",
    "DatasetIssue",
    "DatasetSchema",
    "DatasetSummary",
    "Direction",
    "IngestionResult",
    "IssueSeverity",
    "PreRegistrationStatus",
    "ServiceResult",
    "WarningSeverity",
    "analyze",
    "analyze_experiment",
    "ingest_csv",
]
