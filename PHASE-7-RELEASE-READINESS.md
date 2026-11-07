# Phase 7 release readiness

## Scope and applicability

No separate Phase 7 roadmap was present in the repository. The applicable scope
is therefore the controlled-release work described in the Phase 7 brief:
reproducible Python packaging, operational diagnostics, API compatibility,
quality gates, security review, and release documentation.

The backend API is the release boundary. Docker, persistence, authentication,
and external deployment are not present in the repository and remain deferred.
The legacy JavaScript calculator is a separate static consumer and was not
changed by Phase 7.

## Supported execution

The backend supports Python 3.10 or newer. From the repository root:

```powershell
python -m pip install -e ".\backend[test,lint,api]"
$env:PYTHONPATH = "backend\src"
python -m pytest backend\tests -q
python -m ruff check backend\src backend\tests
python -m mypy backend\src
python -m uvicorn experimentlens.api:app
```

The package is stateless and in-memory. No environment variables or secrets are
required for the current API. No credentials, developer paths, or statistical
parameters are read from global configuration.

## Runtime diagnostics

- `GET /health` returns `{"status":"ok"}` and preserves the existing contract.
- `GET /ready` returns `{"status":"ready"}` for process readiness only; it does
  not evaluate an experiment.
- `GET /version` returns the package name and version.
- `POST /api/v1/analyses` returns full-precision values and stable reason codes.
- Invalid requests return HTTP 422 with `invalid_analysis_request`.
- Unexpected failures return HTTP 500 with `internal_analysis_error`.
- Boundary logs include request ID, route, outcome, status, and duration, but
  never request payloads or experiment identifiers.

## Release validation

The GitHub Actions workflow in `.github/workflows/ci.yml` runs the complete
backend tests, Ruff, mypy, and an sdist/wheel build. The release smoke tests
cover valid, blocked, sparse, invalid, deterministic, and operational-boundary
requests.

The JavaScript project has no committed lockfile and Node.js was unavailable in
the Phase 0 environment, so frontend execution is not claimed as a Phase 7
result. Adding a lockfile and a frontend CI job is deferred until the frontend
runtime/toolchain is intentionally brought under release management.

## Security and limitations

The checked-in backend has no known secret material, unsafe deserialization,
path-based upload endpoint, container configuration, or dependency audit
workflow. Dependency versions remain bounded by the existing project metadata
(`>=` constraints); a lockfile is intentionally not introduced for this
library-style package. A dependency vulnerability scan should be added when a
repository policy or deployment target requires one.

There is no graceful-shutdown hook because the application does not own
long-lived resources. Operational health is deliberately separate from a
blocked or invalid experiment result.

## Status

Phase 7 backend release-readiness work is complete for the applicable surfaces.
External deployment, persistence, authentication, frontend packaging, and
dependency locking remain explicitly deferred.
