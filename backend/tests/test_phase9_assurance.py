"""Phase 9 aggregate-monitoring and deterministic regression sentinels."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

import experimentlens
from experimentlens import api
from experimentlens.api import app
from experimentlens.monitoring import METRIC_SCHEMA, metrics


def _payload() -> dict:
    return {
        "experiment_id": "phase9-sentinel",
        "control": {
            "assignment_count": 1000,
            "records_received": 1000,
            "eligible_count": 1000,
            "success_count": 100,
        },
        "treatment": {
            "assignment_count": 1000,
            "records_received": 1000,
            "eligible_count": 1000,
            "success_count": 150,
        },
        "config": {"mde_value": 0.02},
    }


def test_metrics_classify_analysis_outcomes_without_payloads() -> None:
    metrics.reset()
    client = TestClient(app)

    successful = client.post("/api/v1/analyses", json=_payload())
    assert successful.status_code == 200

    blocked_payload = _payload()
    blocked_payload["control"].update(records_received=1001, duplicate_count=1, excluded_count=1)
    blocked = client.post("/api/v1/analyses", json=blocked_payload)
    assert blocked.status_code == 200
    assert blocked.json()["analysis"]["analysis_status"] == "blocked"

    invalid = client.post("/api/v1/analyses", content="{malformed")
    assert invalid.status_code == 422

    snapshot = client.get("/metrics").json()
    assert snapshot["schema_version"] == "1"
    assert snapshot["metric_schema"] == METRIC_SCHEMA
    assert snapshot["counters"]["analyses_total"] == 2
    assert snapshot["counters"]["analyses_confirmatory_total"] == 1
    assert snapshot["counters"]["analyses_blocked_total"] == 1
    assert snapshot["counters"]["requests_invalid_total"] == 1
    assert snapshot["methods"]["two_proportion_z"] == 2
    assert snapshot["warning_codes"]["duplicate_assignment"] == 1
    assert "phase9-sentinel" not in str(snapshot)

    metrics.reset()


def test_metrics_reset_and_runtime_endpoints_are_explicit() -> None:
    metrics.reset()
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.get("/version").json() == {"name": "experimentlens", "version": "0.1.0"}
    metrics.reset()
    assert client.get("/metrics").json()["counters"] == {}
    assert client.get("/metrics").json()["request_duration_ms"]["count"] == 1
    metrics.reset()


def test_statistical_sentinel_preserves_full_precision_contract() -> None:
    response = TestClient(app).post("/api/v1/analyses", json=_payload())
    analysis = response.json()["analysis"]

    assert analysis["control_rate"] == 0.1
    assert analysis["treatment_rate"] == 0.15
    assert analysis["absolute_lift"] == 0.04999999999999999
    assert analysis["selected_method"] == "two_proportion_z"
    assert analysis["analysis_status"] == "confirmatory"
    assert analysis["verdict"] == "statistically_significant_practical_impact_uncertain"


def test_identical_requests_are_reproducible() -> None:
    client = TestClient(app)
    first = client.post("/api/v1/analyses", json=_payload()).json()
    second = client.post("/api/v1/analyses", json=_payload()).json()

    assert first == second


def test_internal_errors_are_counted_once_and_redacted(monkeypatch) -> None:
    def fail(_experiment):
        raise RuntimeError("private implementation detail")

    metrics.reset()
    monkeypatch.setattr(api, "analyze_experiment", fail)
    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/v1/analyses", json=_payload()
    )

    assert response.status_code == 500
    assert "private implementation detail" not in response.text
    assert metrics.snapshot()["counters"]["requests_internal_error_total"] == 1


def test_metrics_updates_are_thread_safe() -> None:
    metrics.reset()
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: metrics.record_request("success", 2.0), range(1000)))

    snapshot = metrics.snapshot()
    assert snapshot["counters"]["requests_success_total"] == 1000
    assert snapshot["request_duration_ms"] == {"count": 1000, "average": 2.0}
    metrics.reset()


def test_release_manifest_and_constraints_are_consistent() -> None:
    root = Path(__file__).parents[2]
    manifest = json.loads((root / "release-manifest.json").read_text())
    constraints = (root / "backend" / "constraints.txt").read_text()
    ci = (root / ".github" / "workflows" / "ci.yml").read_text()

    assert manifest["package_name"] == "experimentlens"
    assert manifest["package_version"] == experimentlens.__version__
    assert manifest["specification_version"] == "1.0"
    assert manifest["supported_python"] == ["3.10", "3.11", "3.12"]
    assert manifest["dependency_constraints"] == "backend/constraints.txt"
    assert "pip_audit" in manifest["commands"]["dependency_audit"]
    assert "fastapi==" in constraints
    assert "scipy==" in constraints
    assert 'python-version: ["3.10", "3.11", "3.12"]' in ci
    assert "pip install pip-audit" in ci
    assert "pip_audit --local" in ci
