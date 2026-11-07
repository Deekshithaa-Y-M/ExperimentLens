# ExperimentLens statistical core

This package implements the Version 1 two-arm binary experiment contract in
`docs/statistical-specification.md`. It contains typed models, validation and
SRM gates, Wilson/Newcombe intervals, z-test/Fisher method selection, power
planning, and deterministic analysis decisions. It does not expose an API or
modify the legacy JavaScript calculator.

The Phase 5 API boundary is implemented in `experimentlens.api`:

```powershell
python -m pip install -e ".\backend[test,lint,api]"
$env:PYTHONPATH = "backend\src"
python -m uvicorn experimentlens.api:app --reload
```

`POST /api/v1/analyses` accepts a strict JSON request containing `experiment_id`,
`control`, `treatment`, and an optional `config`. Each arm requires assignment,
received-record, eligible, and success counts. `config.mode` is `confirmatory` or
`exploratory`; `mde_type` is currently `absolute`, and all other plan fields have
documented defaults. The response separates the full-precision `analysis` payload
from stable machine-readable `reason_codes`. No display rounding is performed at
the API boundary.

Invalid JSON, schema violations, and domain validation failures return HTTP 422 with
an `invalid_analysis_request` error object and structured details. A valid but
unreliable experiment returns HTTP 200 with `analysis_status = "blocked"` and
`verdict = "cannot_analyze"`; it is never converted into a successful result.
`GET /health` returns `{"status": "ok"}`. `GET /ready` reports process readiness
and `GET /version` reports the package version. `GET /metrics` returns process-local
aggregate request and analysis counters, selected-method and warning-code
frequencies, and aggregate request duration. It does not retain request payloads,
identifiers, or credentials and resets when the process restarts. None of these
operational endpoints evaluates an experiment. Persistence, authentication, and
frontend migration remain deferred.

The backend's tested dependency set is constrained in
`backend/constraints.txt`. The constraints file pins the direct and transitive
packages used by the declared test, lint, and API extras for the supported Python
versions. Regenerate it after dependency changes by reviewing a complete
`python -m pip freeze --all` from the target environment, retaining only
backend requirements, then rerun the full matrix checks. The machine-readable
release evidence is in `release-manifest.json`; its `source_revision` is filled
by a release process when an artifact is built from a commit.

CI tests Python 3.10, 3.11, and 3.12 using the constraints file, runs the
complete test/lint/type/build checks, verifies importability, and installs
`pip-audit` before running `python -m pip_audit --local` on Python 3.12.
Audit findings must be triaged
before release: upgrade the constrained package, document a narrowly scoped
exception with owner and expiry, or stop the release. The repository has no
deployment target, so package validation is not a rollback rehearsal.

## Raw CSV ingestion

The reusable ingestion layer is in
`experimentlens.ingestion`, with typed models in `dataset_models.py` and value
validators in `dataset_validation.py`. The canonical CSV columns are
`user_id`, `group`, `converted`, and `timestamp`; `revenue`, `device`, `country`,
`traffic_source`, and `pre_experiment_value` are optional. Unknown columns are
preserved and reported as informational issues. A `DatasetSchema` can map
alternative source names:

```python
schema = DatasetSchema(
    required_columns=("id", "arm", "outcome", "at"),
    user_id_column="id",
    group_column="arm",
    conversion_column="outcome",
    timestamp_column="at",
)
config = DatasetConfig(start, end, schema=schema)
result = ingest_csv(file_like_object, config)
```

Timestamps must include an explicit timezone and are normalized to UTC. The
registered interval is `[experiment_start, experiment_end)`. Only literal
`0`/`1` conversion values are accepted. Duplicate users are reported as
blocking and excluded from eligible units; users occurring in both groups are
reported separately, categorized as `cross_group`, and excluded from both arms.
Exclusion categories are mutually exclusive **row-based** counts. Their sum
always equals `rows_excluded`; the precedence is missing, invalid,
outside-window, duplicate, then cross-group. Arm-level `excluded_count` and
`exclusion_rate` include contamination rows and use
`excluded_count / records_received` (or `None` when no records were received).
Assignment counts remain unique valid in-window users before conversion
filtering, so they can be passed to the Phase 3 SRM logic.
`result.summary.to_arm_counts()` returns the two compatible `ArmCounts` values.
Ingestion does not calculate a statistical verdict.

Run ingestion tests with:

```powershell
$env:PYTHONPATH = "backend\src"
python -m pytest backend\tests\test_ingestion.py backend\tests\test_dataset_validation.py -q
```

The current implementation is CSV-only, keeps normalized records in memory, and
does not persist uploads or implement a file-upload HTTP endpoint.

Example valid request:

```json
{
  "experiment_id": "checkout-button-2026-10",
  "control": {
    "assignment_count": 1000,
    "records_received": 1000,
    "eligible_count": 1000,
    "success_count": 100
  },
  "treatment": {
    "assignment_count": 1000,
    "records_received": 1000,
    "eligible_count": 1000,
    "success_count": 150
  },
  "config": {"mode": "confirmatory", "mde_value": 0.02}
}
```

The response contains `analysis.analysis_status`, `analysis.verdict`,
`analysis.warnings`, full-precision rates/effects/intervals/p-values, and
`reason_codes`, for example `["confirmatory_interpretation",
"statistically_significant", "method_two_proportion_z"]`.

A blocked result still returns a structured analysis response:

```json
{
  "analysis": {
    "analysis_status": "blocked",
    "reliability": "blocked",
    "verdict": "cannot_analyze",
    "warnings": [{"code": "srm_failure", "severity": "blocking"}]
  },
  "reason_codes": ["data_quality_blocked", "srm_failure", "cannot_analyze"]
}
```

An invalid request returns HTTP 422 without running analysis:

```json
{
  "error": {
    "code": "invalid_analysis_request",
    "message": "Request validation failed",
    "details": [{"location": ["control", "success_count"], "message": "...", "type": "..."}]
  }
}
```

### Operational behavior

The API emits structured boundary logs through the `experimentlens.api` logger.
Events include `request_started`, `request_completed`, validation failures,
blocked analyses, and unexpected internal failures. Logs contain a generated
or validated `request_id`, route, status, outcome, and duration; request
payloads, experiment identifiers, and credentials are not logged. A caller may
provide an `X-Request-ID` containing up to 64 alphanumeric, period, underscore,
or hyphen characters.

Malformed or domain-invalid requests return the stable HTTP 422 error shape
above. Unexpected internal failures return HTTP 500 with
`internal_analysis_error` and do not expose stack traces or implementation
details. The analysis workflow remains in-memory and stateless, so repeated
requests with the same input produce the same serialized result.

### Reliability audit

Each analysis includes a deterministic `reliability_audit` with typed findings,
stable `audit_reason_codes`, checked categories, evidence, and remediation.
Finding severities are `info`, `warning`, and `blocking`; any blocking finding
sets audit reliability to `blocked`, while warnings set it to
`review_recommended`. Duplicate assignments, confirmatory cross-group
contamination, exclusion failures, and blocking SRM failures are blocking.
SRM deviation above the configured warning threshold without a blocking
p-value is review-recommended. Underpowered or unavailable planning is
reported separately and does not become a data-quality block.

Version 1 audits multiplicity and stopping controls but does not implement
multiple-comparison correction or sequential inference. More than one
confirmatory hypothesis without a declared adjustment, unauthorized interim
looks, optional stopping, unsupported stopping rules, or missing
pre-registration are blocking. Exploratory multiplicity and interim looks are
reported as review findings and never receive a confirmatory verdict.

`excluded_count` is the total policy-exclusion numerator and must include the
missing, invalid, and duplicate category counts. SRM always uses assignment
counts. For non-1:1 allocation, planning searches integer arm-size pairs and
checks planned two-sided normal-approximation power; planning unavailability
leaves valid descriptive/statistical results available while marking design
status unavailable.

`metric_direction` describes which conversion-rate direction is better, while
`mde_direction` describes the pre-registered practical effect being tested; they
are intentionally independent. `valid_count` defaults to `eligible_count` for
backward-compatible construction and may be supplied explicitly when raw valid
records and eligible units differ. The non-1:1 planner uses a maximum total
search bound of 2,000,000 and an allocation tolerance of one unit divided by
the candidate total; both are included in planning metadata.

From the repository root:

```powershell
python -m pip install -e ".\backend[test,lint]"
$env:PYTHONPATH = "backend\src"
python -m pytest backend\tests -q
ruff check backend\src backend\tests
python -m mypy backend\src
```

The release boundary and CI quality gates are documented in
`PHASE-7-RELEASE-READINESS.md`.
