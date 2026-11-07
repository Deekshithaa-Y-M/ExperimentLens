# Phase 9 post-release assurance

## Scope and applicability

The repository contains no separate Phase 9 roadmap. The applicable scope is
the post-release assurance brief: runtime health, safe aggregate analysis
monitoring, deterministic statistical sentinels, reproducibility, dependency
review, incident readiness, and maintenance evidence. The existing Phase 8
implementation already provides `/health`, `/ready`, `/version`, structured
redacted logs, and a stateless API boundary.

| Workstream | Status | Evidence or limitation |
|---|---|---|
| Process health/readiness/version | PASS | Existing endpoints are deterministic and separate from experiment status; runtime tests cover all three. |
| Analysis-quality monitoring | PASS | `/metrics` exposes a centrally documented, typed process-local metric schema and aggregate counters only. |
| Input/allocation drift | NOT APPLICABLE | No persisted or reference aggregate population exists; no drift claim is made. |
| Statistical regression sentinels | PASS | `backend/tests/test_phase9_assurance.py` supplements the existing reference suites. |
| Reproducibility | PASS | Identical public requests produce identical serialized responses. |
| Dependency/environment drift | IMPLEMENTED AND VERIFIED | `backend/constraints.txt` pins the tested backend set; CI covers Python 3.10, 3.11, and 3.12, verifies import/build, and audits the installed dependency set. |
| Incident readiness | PASS | Response procedure below is documented for the available stateless boundary. |
| External alerting/routing | DOCUMENTED POLICY ONLY | No alert destination or monitoring platform is configured; recommended thresholds are below. |
| Auditability/change tracking | PASS | Version endpoint, specification version, reason codes, CI, and release reports identify behavior. |
| Maintenance/rollback | NOT APPLICABLE FOR REHEARSAL | Wheel/sdist recovery and verification procedure is documented below; no deployment target exists to rehearse. |
| Privacy/data minimization | PASS | Metrics and logs exclude experiment identifiers and raw payloads. |

## Monitoring contract

`GET /metrics` is an in-memory diagnostic snapshot. It contains request outcome
counters, analysis status counters, evidence-status counts, selected-method
counts, warning-code counts, and aggregate request duration. It does not retain
request IDs, experiment identifiers, counts, or payloads. Values reset on process
restart and are not a durable business record.

The response includes `schema_version` and `metric_schema`. Metric families are
typed as counters or gauges, use requests/analyses/warnings/milliseconds as
units, and identify whether future alerting is suitable. Updates are protected
by a process lock and snapshots are consistent. `requests_<outcome>_total`,
`analyses_total`, and `analyses_<status>_total` are counters; the grouped
warning, method, and evidence maps are counter maps; `request_duration_ms` is
an aggregate gauge containing sample count and arithmetic mean. All values are
process-local and reset on restart or explicit test reset.

Blocked analyses are counted as analyses with `blocked` status, not as process
outages. Invalid requests are counted separately from successful analyses.
This endpoint is suitable for local verification and a future adapter, not an
external alerting system.

## Sentinels and thresholds

The Phase 9 sentinel suite uses fixed request fixtures and exact categorical
expectations. Rates and the absolute lift use the serialized full-precision
values; no rounded value drives a decision. Repeated identical requests are
required to have equivalent JSON structures across the initial response and
replay.

No production alert is active. The following are policy recommendations for a
future deployment adapter, not measured results:

| Signal | Suggested threshold/window | Severity | Operator action |
|---|---|---|---|
| `requests_internal_error_total` rate | >1% of requests over 5 minutes, minimum 20 requests | HIGH | Check version/logs, contain release, run smoke test. |
| HTTP 500 responses | 5 or more in 5 minutes | HIGH | Inspect safe error logs and remove affected release if persistent. |
| `/health` or `/ready` | 3 consecutive failures over 2 minutes | CRITICAL | Check process/dependencies and restore last-known-good artifact. |
| Invalid requests | >20% over 15 minutes, minimum 50 requests | MEDIUM | Check client/schema rollout; do not treat as service success. |
| Blocked analyses | 2x established 24-hour baseline, minimum 20 analyses | MEDIUM | Investigate input/allocation quality and warning-code mix. |
| Statistical sentinel failure | Any failure in release validation | CRITICAL | Stop release or roll back; add regression coverage. |
| Dependency vulnerability | Confirmed high/critical finding in `pip-audit` | HIGH | Stop release, upgrade/replace dependency, or record approved exception. |

These thresholds require a future retained metric adapter and explicit baseline;
they are not evaluated by this stateless repository.

## Incident procedure

1. **Detect:** inspect `/health`, `/ready`, `/version`, safe logs, and aggregate
   `/metrics`; classify elevated internal errors, sentinel failures, output
   drift, or dependency findings as incidents.
2. **Contain:** stop the affected process or remove the release from service
   where the deployment owner permits; do not disable statistical quality gates
   or collect raw payloads.
3. **Collect evidence:** record version, specification version, dependency
   manifest, configuration, request status counts, warning/method counts, and
   relevant redacted logs.
4. **Investigate:** reproduce with the smallest fixed fixture, compare against
   `docs/statistical-specification.md`, and identify whether the issue is
   runtime, integration, dependency, or statistical-contract related.
5. **Recover:** identify the deployed version, select the last-known-good wheel
   or sdist, stop/remove the affected service according to its deployment
   platform, and install/deploy the previous artifact. This repository has no
   deployment target, so this procedure is documented only and is owned by the
   deployment operator.
6. **Verify:** check `/health`, `/ready`, and `/version`, run release smoke tests,
   then run the focused Phase 9 tests, complete backend suite, Ruff, mypy, and
   package build.
7. **Follow up:** record affected versions and the incident, add a regression test
   for every defect, update this runbook
   and the release report, and communicate impact without retaining sensitive
   experiment data.

Severity is critical for a confirmed statistical-contract regression, high for
unavailable health or repeated internal errors, medium for warning/quality
anomaly spikes, and low for documentation or non-blocking dependency drift.
These classifications are procedural; no production alert is claimed.

## Validation commands

```powershell
$env:PYTHONPATH = "backend\src"
python -m pip install --constraint backend\constraints.txt -e ".\backend[test,lint,api]" build
python -m pytest backend\tests\test_phase9_assurance.py -q
python -m pytest backend\tests -q
python -m ruff check backend\src backend\tests
python -m mypy backend\src
python -m pip install pip-audit
python -m pip_audit --local
Set-Location backend
python -m build --wheel --sdist
```

The machine-readable [release manifest](./release-manifest.json) records the
package/specification versions, supported runtimes, constraints reference,
artifact names, and validation commands. `source_revision` is intentionally
`null` in the working tree and must be populated by a commit-based release
process; no local path or user data is recorded.

## Corrective-pass evidence

- The constrained isolated Python 3.12 environment ran `98 passed`, Ruff,
  mypy (`19 source files`), and `python -m pip_audit --local` with
  `No known vulnerabilities found`.
- The package build produced
  `experimentlens-0.1.0-py3-none-any.whl` and
  `experimentlens-0.1.0.tar.gz`.
- A Python 3.10 binary-only resolver check selected the constrained runtime,
  test, lint, and API packages successfully. The first attempt exposed the
  incompatible `scipy-stubs>=1.17` metadata floor; lowering the declared lint
  floor to `>=1.15` and pinning `1.15.3.0` resolved it without dropping Python
  3.10 support.
- The initial audit exposed thirteen advisories in six old constrained packages.
  Those pins were upgraded; the final audit passed with no known vulnerabilities.
- CI YAML parsed successfully. The repository has no hosted CI result in this
  environment, so matrix execution on all three hosted runners remains CI-owned
  evidence rather than a local claim.

## Remaining limitations

Telemetry remains process-local and resets on restart; no baseline dataset or
external alert route exists. Dependencies are constrained, but this is not a
universal lockfile for every platform. CI now runs the declared Python 3.10–3.12
matrix and `pip-audit` against the installed set. Rollback rehearsal remains
not applicable until a deployment target exists. Durable telemetry, active
alert routing, and deployment automation are deferred by scope; no new
statistical method or contract behavior was introduced.
