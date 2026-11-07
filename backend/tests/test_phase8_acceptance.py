"""Phase 8 public-boundary acceptance checks."""

import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from experimentlens.api import app


def _payload() -> dict:
    return {
        "experiment_id": "phase8-acceptance",
        "control": {
            "assignment_count": 10_000,
            "records_received": 10_000,
            "eligible_count": 10_000,
            "success_count": 1_000,
        },
        "treatment": {
            "assignment_count": 10_000,
            "records_received": 10_000,
            "eligible_count": 10_000,
            "success_count": 1_500,
        },
        "config": {"mde_value": 0.02},
    }


def test_public_workflow_covers_direction_modes_and_blocking_precedence() -> None:
    for direction, expected_verdict in (
        ("higher", "positive_result"),
        ("lower", "statistically_significant_practically_weak"),
        ("either", "positive_result"),
    ):
        payload = _payload()
        payload["config"]["mde_direction"] = direction
        response = TestClient(app).post("/api/v1/analyses", json=payload)

        assert response.status_code == 200
        analysis = response.json()["analysis"]
        assert analysis["verdict"] == expected_verdict
        assert analysis["analysis_status"] == "confirmatory"
        assert analysis["control_rate"] == 0.1
        assert analysis["treatment_rate"] == 0.15

    blocked = _payload()
    blocked["control"].update(records_received=9_000, eligible_count=8_000, excluded_count=1_000)
    blocked_response = TestClient(app).post("/api/v1/analyses", json=blocked)
    assert blocked_response.status_code == 200
    assert blocked_response.json()["analysis"]["verdict"] == "cannot_analyze"
    assert blocked_response.json()["analysis"]["analysis_status"] == "blocked"


def test_mixed_sequential_requests_do_not_contaminate_results() -> None:
    client = TestClient(app)
    valid = client.post("/api/v1/analyses", json=_payload())
    malformed = client.post("/api/v1/analyses", content="{malformed")
    valid_again = client.post("/api/v1/analyses", json=_payload())

    assert valid.status_code == valid_again.status_code == 200
    assert valid.json() == valid_again.json()
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "invalid_analysis_request"


def test_concurrent_requests_are_independent() -> None:
    def submit(index: int) -> tuple[int, str, float]:
        payload = _payload()
        payload["experiment_id"] = f"phase8-{index}"
        response = TestClient(app).post("/api/v1/analyses", json=payload)
        body = response.json()
        return response.status_code, body["experiment_id"], body["analysis"]["p_value"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(submit, range(16)))

    assert all(status == 200 for status, _, _ in results)
    assert {experiment_id for _, experiment_id, _ in results} == {
        f"phase8-{index}" for index in range(16)
    }
    assert len({p_value for _, _, p_value in results}) == 1


def test_request_id_and_logs_are_redacted(caplog) -> None:
    caplog.set_level(logging.INFO, logger="experimentlens.api")
    secret_experiment_id = "do-not-log-this"
    payload = _payload()
    payload["experiment_id"] = secret_experiment_id

    response = TestClient(app).post(
        "/api/v1/analyses",
        headers={"X-Request-ID": "phase8-request"},
        json=payload,
    )

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert "request_started" in messages
    assert "request_completed" in messages
    assert all(record.request_id == "phase8-request" for record in caplog.records)
    assert all(secret_experiment_id not in record.getMessage() for record in caplog.records)
