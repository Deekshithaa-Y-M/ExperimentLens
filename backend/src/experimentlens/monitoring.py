"""Safe, process-local aggregate monitoring for the API boundary."""

from collections import Counter
from threading import Lock
from typing import Any, Literal, TypedDict

MetricKind = Literal["counter", "gauge"]


class MetricDefinition(TypedDict):
    """Public metadata for one process-local metric family."""

    kind: MetricKind
    unit: str
    meaning: str
    alert_suitable: bool


METRIC_SCHEMA: dict[str, MetricDefinition] = {
    "requests_<outcome>_total": {
        "kind": "counter",
        "unit": "requests",
        "meaning": "Requests classified by boundary outcome.",
        "alert_suitable": True,
    },
    "analyses_total": {
        "kind": "counter",
        "unit": "analyses",
        "meaning": "Valid analysis requests completed, including blocked analyses.",
        "alert_suitable": True,
    },
    "analyses_<status>_total": {
        "kind": "counter",
        "unit": "analyses",
        "meaning": "Valid analyses grouped by confirmatory, exploratory, or blocked status.",
        "alert_suitable": True,
    },
    "evidence_statuses": {
        "kind": "counter",
        "unit": "analyses",
        "meaning": "Valid analyses grouped by evidence status.",
        "alert_suitable": False,
    },
    "methods": {
        "kind": "counter",
        "unit": "analyses",
        "meaning": "Valid analyses grouped by selected statistical method.",
        "alert_suitable": False,
    },
    "warning_codes": {
        "kind": "counter",
        "unit": "warnings",
        "meaning": "Warning occurrences grouped by stable warning code.",
        "alert_suitable": True,
    },
    "request_duration_ms": {
        "kind": "gauge",
        "unit": "milliseconds",
        "meaning": "Count and arithmetic mean of observed boundary request durations.",
        "alert_suitable": True,
    },
}


class AnalysisMetrics:
    """Collect bounded aggregate counters without retaining request payloads."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()
        self._warning_codes: Counter[str] = Counter()
        self._method_codes: Counter[str] = Counter()
        self._status_codes: Counter[str] = Counter()
        self._duration_ms_total = 0.0
        self._duration_samples = 0

    def record_request(self, outcome: str, duration_ms: float) -> None:
        with self._lock:
            self._counters[f"requests_{outcome}_total"] += 1
            self._duration_ms_total += duration_ms
            self._duration_samples += 1

    def record_analysis(
        self,
        *,
        analysis_status: str,
        evidence_status: str,
        method: str | None,
        warning_codes: tuple[str, ...],
    ) -> None:
        with self._lock:
            self._counters["analyses_total"] += 1
            self._counters[f"analyses_{analysis_status}_total"] += 1
            self._status_codes[evidence_status] += 1
            if method is not None:
                self._method_codes[method] += 1
            for warning_code in warning_codes:
                self._warning_codes[warning_code] += 1

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-safe snapshot containing aggregate values only."""
        with self._lock:
            average_duration = (
                self._duration_ms_total / self._duration_samples
                if self._duration_samples
                else 0.0
            )
            return {
                "schema_version": "1",
                "metric_schema": METRIC_SCHEMA,
                "counters": dict(sorted(self._counters.items())),
                "warning_codes": dict(sorted(self._warning_codes.items())),
                "evidence_statuses": dict(sorted(self._status_codes.items())),
                "methods": dict(sorted(self._method_codes.items())),
                "request_duration_ms": {
                    "count": self._duration_samples,
                    "average": average_duration,
                },
            }

    def reset(self) -> None:
        """Clear process-local values for isolated tests or controlled restarts."""
        with self._lock:
            self._counters.clear()
            self._warning_codes.clear()
            self._method_codes.clear()
            self._status_codes.clear()
            self._duration_ms_total = 0.0
            self._duration_samples = 0


metrics = AnalysisMetrics()
