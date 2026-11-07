# Phase 8 release certification

## Status

**PASS for the applicable backend release boundary, with documented limitations.**
The statistical contract was not changed. The repository has no separate Phase 8
roadmap, so the Phase 8 brief supplied for this release was used as the scope.

## Scope and applicability

| Workstream | Status | Evidence and decision |
|---|---|---|
| End-to-end public acceptance | PASS | `backend/tests/test_phase8_acceptance.py`, `backend/tests/test_api.py`, 91 backend tests |
| Statistical acceptance replay | PASS | Reference comparisons, known values, boundary tests, and fixed-seed simulations |
| Clean/isolated execution | PASS with limitation | Wheel installed into an isolated virtual environment; runtime dependencies reused from system-site packages |
| Operational rehearsal | PASS | Uvicorn startup, `/health`, `/ready`, `/version`, request processing, and controlled stop |
| Reliability/resilience | PASS | Sequential mixed requests, repeated deterministic requests, concurrent requests, malformed payloads, sparse/degenerate data, and large counts |
| Security acceptance | PASS | Focused review found no vulnerabilities |
| Observability/audit evidence | PASS | Request IDs, lifecycle logs, blocked-result logs, safe validation/internal errors, and redaction tests |
| Documentation/runbook | PASS | `backend/README.md` and Phase 7 release documentation match the implemented API |
| Release/package certification | PASS | Wheel and sdist build successfully; artifact contents include package and tests |
| Rollback certification | NOT APPLICABLE | No rollback mechanism or deployed target exists in this repository; limitation remains explicit |
| Frontend release validation | NOT APPLICABLE | The legacy JavaScript calculator is a separate consumer and has no committed Node lockfile/toolchain |
| External deployment, persistence, authentication | NOT APPLICABLE | These surfaces are not implemented or required by the current release boundary |

## Acceptance evidence

The Phase 8 suite verifies:

- Confirmatory positive, direction-sensitive, blocked, and malformed requests.
- Higher, lower, and either MDE directions.
- Exact HTTP status and structured error/analysis response shapes.
- Full-precision rate and p-value fields.
- Repeated identical requests and mixed valid/invalid request isolation.
- Sixteen concurrent requests without cross-request contamination.
- Request-ID propagation and experiment-ID log redaction.

Existing suites additionally verify sparse and degenerate Fisher selection,
SRM/data-quality precedence, alpha and MDE equality boundaries, rounding
independence, SciPy reference values, fixed-seed false-positive/coverage/power
evidence, and package release smoke behavior.

## Commands and results

Executed from the repository root unless noted:

```powershell
$env:PYTHONPATH = "backend\src"
python -m pytest backend\tests\test_phase8_acceptance.py -q
# 4 passed

python -m pytest backend\tests -q
# 91 passed

python -m ruff check backend\src backend\tests
# All checks passed

python -m mypy backend\src
# Success: no issues found in 17 source files

Set-Location backend
python -m build --wheel --sdist
# Successfully built experimentlens-0.1.0-py3-none-any.whl and
# experimentlens-0.1.0.tar.gz
```

The wheel was installed with `pip --no-deps` into a fresh virtual environment
using shared system packages, then imported successfully and exercised through
`TestClient`. A real Uvicorn process started successfully and returned:

```text
GET /health  -> 200 {"status":"ok"}
GET /ready   -> 200 {"status":"ready"}
GET /version -> 200 {"name":"experimentlens","version":"0.1.0"}
```

## Thresholds

- Categorical API outcomes: exact status, verdict, analysis status, and error
  code assertions.
- Numerical reference checks: existing explicit absolute and relative
  tolerances in `backend/tests/test_reference_comparisons.py`.
- Simulation checks: existing fixed-seed 2,000-replication thresholds for
  false-positive rate, interval coverage, power, and SRM detection.
- Concurrency: 16 requests across 8 workers; all HTTP 200, unique experiment
  identifiers, and identical p-values.
- Build/runtime: successful wheel and sdist creation, import, startup, health,
  readiness, version, and controlled shutdown.

## Changes and findings

Only one file was added:

- `backend/tests/test_phase8_acceptance.py` — focused public-boundary acceptance
  and resilience coverage.

No dependencies, statistical formulas, thresholds, production API behavior, or
configuration were changed. No release-blocking defect was found. The only
observed command issue was an initial attempt to run `python -m build` from the
repository root; the package root is `backend`, and the documented backend
command succeeds there. The first runtime probe raced startup; the subsequent
probe after the documented startup log returned all expected responses.

## Remaining limitations and deferred work

- Dependency versions remain range-based and no lockfile or dependency audit
  workflow is configured.
- The isolated runtime check reused system-site packages; a fully network-isolated
  dependency resolution test was not claimed.
- There is no deployment target, rollback command, persistence, authentication,
  or graceful-shutdown hook for this stateless in-memory service.
- Frontend build/release validation remains deferred because the repository has
  no committed Node toolchain or lockfile.
