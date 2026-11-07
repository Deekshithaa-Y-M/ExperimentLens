import json
import logging

from fastapi.testclient import TestClient

from experimentlens import api
from experimentlens.api import app

client = TestClient(app)


def request_payload(**overrides):
    payload = {
        "experiment_id": "api-example",
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
    payload.update(overrides)
    return payload


def test_health_and_valid_analysis_response():
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post("/api/v1/analyses", json=request_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["experiment_id"] == "api-example"
    assert body["analysis"]["analysis_status"] == "confirmatory"
    assert body["analysis"]["control_rate"] == 0.1
    assert body["analysis"]["treatment_rate"] == 0.15
    assert "method_two_proportion_z" in body["reason_codes"]
    assert body["analysis"]["reliability_audit"]["overall_reliability"] == "review_recommended"
    assert body["analysis"]["audit_reason_codes"] == ["underpowered"]


def test_exploratory_analysis_has_no_confirmatory_verdict():
    response = client.post(
        "/api/v1/analyses",
        json=request_payload(config={"mode": "exploratory"}),
    )
    assert response.status_code == 200
    body = response.json()["analysis"]
    assert body["analysis_status"] == "exploratory"
    assert body["verdict"] is None


def test_blocked_quality_gate_has_structured_reason_codes():
    payload = request_payload()
    payload["control"]["records_received"] = 100
    payload["control"]["eligible_count"] = 94
    payload["control"]["success_count"] = 10
    payload["control"]["excluded_count"] = 6
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["analysis_status"] == "blocked"
    assert body["analysis"]["verdict"] == "cannot_analyze"
    assert "exclusion_rate_exceeded" in body["reason_codes"]
    assert "data_quality_blocked" in body["reason_codes"]


def test_invalid_requests_are_structured_and_do_not_run_analysis():
    payload = request_payload()
    payload["control"]["success_count"] = 1.5
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_analysis_request"
    assert error["details"]


def test_domain_constraints_are_structured():
    payload = request_payload()
    payload["control"]["success_count"] = 1001
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis_request"


def test_invalid_mode_and_relative_mde_are_rejected():
    for config in ({"mode": "invalid"}, {"mde_type": "relative"}):
        response = client.post(
            "/api/v1/analyses",
            json=request_payload(config=config),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_analysis_request"


def test_api_exposes_multiple_testing_and_stopping_audit():
    response = client.post(
        "/api/v1/analyses",
        json=request_payload(config={
            "hypothesis_count": 2,
            "primary_hypothesis_count": 2,
            "interim_looks": 1,
        }),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["analysis_status"] == "blocked"
    assert set(body["analysis"]["audit_reason_codes"]) >= {
        "multiple_primary_hypotheses",
        "unauthorized_interim_look",
    }
    assert body["analysis"]["reliability_audit"]["blocking"] is True


def test_api_exploratory_audit_is_review_recommended():
    response = client.post(
        "/api/v1/analyses",
        json=request_payload(config={
            "mode": "exploratory",
            "hypothesis_count": 2,
            "interim_looks": 1,
            "cross_group_count": 1,
        }),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["analysis"]["analysis_status"] == "exploratory"
    assert body["analysis"]["reliability"] == "review_recommended"
    assert body["analysis"]["verdict"] is None


def test_deterministic_full_precision_response():
    payload = request_payload()
    first = client.post("/api/v1/analyses", json=payload)
    second = client.post("/api/v1/analyses", json=payload)
    assert first.json() == second.json()
    assert first.json()["analysis"]["p_value"] < 0.001


def test_invalid_boundary_shapes_are_rejected_without_analysis():
    payload = request_payload()
    payload["unexpected"] = True
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis_request"

    response = client.post("/api/v1/analyses", content="{malformed")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis_request"

    payload = request_payload()
    payload["control"]["success_count"] = None
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 422

    payload = request_payload()
    payload["control"]["assignment_count"] = -1
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 422


def test_non_finite_configuration_is_rejected():
    payload = json.dumps(request_payload(config={"mde_value": float("inf")}))
    response = client.post(
        "/api/v1/analyses",
        content=payload,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_analysis_request"


def test_blocked_and_sparse_results_remain_explicit():
    blocked = request_payload()
    blocked["treatment"]["assignment_count"] = 10
    blocked["treatment"]["records_received"] = 10
    blocked["treatment"]["eligible_count"] = 10
    blocked["treatment"]["success_count"] = 1
    response = client.post("/api/v1/analyses", json=blocked)
    assert response.status_code == 200
    assert response.json()["analysis"]["analysis_status"] == "blocked"
    assert response.json()["analysis"]["verdict"] == "cannot_analyze"

    sparse = request_payload()
    for arm in (sparse["control"], sparse["treatment"]):
        arm.update(
            assignment_count=4,
            records_received=4,
            eligible_count=4,
            success_count=0,
        )
    response = client.post("/api/v1/analyses", json=sparse)
    assert response.status_code == 200
    assert response.json()["analysis"]["selected_method"] == "fisher_exact"


def test_large_valid_counts_remain_serializable():
    payload = request_payload()
    for arm, success_count in ((payload["control"], 100_000_000), (payload["treatment"], 120_000_000)):
        arm.update(
            assignment_count=1_000_000_000,
            records_received=1_000_000_000,
            eligible_count=1_000_000_000,
            success_count=success_count,
        )
    response = client.post("/api/v1/analyses", json=payload)
    assert response.status_code == 200
    assert response.json()["analysis"]["control_rate"] == 0.1
    assert response.json()["analysis"]["treatment_rate"] == 0.12


def test_boundary_logging_uses_request_id_without_payload(caplog):
    caplog.set_level(logging.INFO, logger="experimentlens.api")
    response = client.post(
        "/api/v1/analyses",
        headers={"X-Request-ID": "phase6-test"},
        json=request_payload(),
    )
    assert response.status_code == 200
    messages = [record.message for record in caplog.records]
    assert "request_started" in messages
    assert "request_completed" in messages
    assert all(record.request_id == "phase6-test" for record in caplog.records)
    assert all("api-example" not in record.getMessage() for record in caplog.records)


def test_unexpected_errors_return_safe_error_response(monkeypatch):
    def fail(_experiment):
        raise RuntimeError("internal detail that must not be exposed")

    monkeypatch.setattr(api, "analyze_experiment", fail)
    isolated_client = TestClient(app, raise_server_exceptions=False)
    response = isolated_client.post("/api/v1/analyses", json=request_payload())
    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_analysis_error",
            "message": "The analysis could not be completed.",
        }
    }
    assert "internal detail" not in response.text
