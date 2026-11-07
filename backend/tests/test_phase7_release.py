"""Release-boundary smoke tests for the public API."""

from fastapi.testclient import TestClient

from experimentlens import __version__
from experimentlens.api import app

client = TestClient(app)


def _payload() -> dict:
    return {
        "experiment_id": "release-smoke",
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
    }


def test_operational_endpoints_are_distinct_from_analysis_status() -> None:
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.get("/version").json() == {
        "name": "experimentlens",
        "version": __version__,
    }


def test_valid_analysis_preserves_full_precision_and_is_deterministic() -> None:
    first = client.post("/api/v1/analyses", json=_payload())
    second = client.post("/api/v1/analyses", json=_payload())

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["analysis"]["control_rate"] == 0.1
    assert first.json()["analysis"]["treatment_rate"] == 0.15
    assert first.json()["analysis"]["p_value"] < 0.05


def test_blocked_sparse_and_invalid_inputs_keep_stable_boundaries() -> None:
    blocked = _payload()
    blocked["control"].update(
        records_received=100,
        eligible_count=94,
        success_count=10,
        excluded_count=6,
    )
    blocked_response = client.post("/api/v1/analyses", json=blocked)
    assert blocked_response.status_code == 200
    assert blocked_response.json()["analysis"]["analysis_status"] == "blocked"
    assert blocked_response.json()["analysis"]["verdict"] == "cannot_analyze"

    sparse = _payload()
    for arm in (sparse["control"], sparse["treatment"]):
        arm.update(assignment_count=4, records_received=4, eligible_count=4, success_count=0)
    sparse_response = client.post("/api/v1/analyses", json=sparse)
    assert sparse_response.status_code == 200
    assert sparse_response.json()["analysis"]["selected_method"] == "fisher_exact"

    invalid = _payload()
    invalid["control"]["success_count"] = 1.5
    invalid_response = client.post("/api/v1/analyses", json=invalid)
    assert invalid_response.status_code == 422
    assert invalid_response.json()["error"]["code"] == "invalid_analysis_request"
