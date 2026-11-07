# ExperimentLens Statistical Specification

**Status:** Normative  
**Version:** 1.0  
**Scope:** Version 1 supports two-arm randomized experiments with binary conversion metrics.

This document is the statistical contract for ExperimentLens. Production calculations,
statuses, warnings, and verdicts must follow it. Display rounding must never change a
calculation or decision; never use rounded confidence values for decisions. The
existing calculator's rounded-confidence threshold and
silent zero-visitor behavior are legacy behavior and are superseded by this
specification.

## 1. Version 1 scope

Version 1 supports:

- Two mutually exclusive arms: control and treatment.
- Binary conversion metrics with one outcome per randomization unit.
- Two-proportion statistical testing.
- Fisher's exact test for sparse 2x2 tables.
- Wilson intervals for individual proportions.
- Newcombe intervals for the difference between proportions.
- Absolute lift and descriptive relative lift where defined.
- Power and sample-size checks.
- Data-quality and reliability auditing.
- Simulation-based validation of statistical behavior.

The following are explicitly deferred to Version 2:

- Continuous metrics, Welch's t-test, and bootstrap intervals for continuous metrics.
- Revenue metrics, unless represented as a future metric extension.
- Bayesian analysis, CUPED, bandits, and sequential methods.

### Future Version 2 methods

A future continuous-metric implementation may use Welch's t-test and bootstrap
confidence intervals. A bootstrap interval is reproducible when the seed, algorithm,
replicate count, input data, and software configuration are fixed. Small samples may
make bootstrap intervals unstable or imprecise, but small sample size does not
automatically make them non-reproducible. Small samples must produce a warning or
violate a documented minimum-sample rule, not trigger an unexplained
`cannot_analyze` result.

## 2. Experiment definition

Each analysis describes one pre-registered experiment and exactly two mutually
exclusive arms.

| Field | Requirement |
|---|---|
| Experiment identifier | Stable identifier for the experiment and analysis run. |
| Control group | Baseline experience, labeled `control`; its conversion rate is the reference. |
| Treatment group | Changed experience, labeled `treatment`; its conversion rate is compared with control. |
| Randomization unit | Entity assigned to an arm, normally one user. Each unit must have one assignment. |
| Start/end | Timezone-aware timestamps defining the half-open interval `[start_time, end_time)`. |
| Primary metric | Exactly one pre-specified binary conversion metric; it receives the confirmatory verdict. |
| Secondary metrics | Optional pre-specified metrics; descriptive by default in Version 1. |
| Expected allocation | Pre-specified treatment-to-control allocation ratio, default `1:1`. |
| Pre-registration | Metric, alpha, tail, MDE, power, allocation, stopping rule, and data-quality policy recorded before outcome inspection. |

Assignments must be independent of outcomes. Post-treatment exclusions,
reassignment, treatment contamination, or changing the primary metric after observing
results invalidate a confirmatory interpretation.

### Time-window semantics

The analysis interval is `[start_time, end_time)`:

- A record exactly at `start_time` is included.
- A record exactly at `end_time` is excluded.
- `end_time` must be strictly later than `start_time`.
- Input timestamps must be timezone-aware.
- Valid timestamps are normalized to UTC before filtering.
- Invalid or timezone-naive timestamps are rejected as invalid records; an integration
  may instead normalize them only under an explicitly documented, pre-analysis
  timezone policy. No silent local-time assumption is allowed.

### Binary metric definition

Each eligible unit contributes one outcome `Y in {0, 1}`. For arm `g`:

```text
n_g = eligible units
x_g = successes
p_g = x_g / n_g
```

`p_g` is estimable only when `n_g > 0`. A zero eligible-unit count is undefined, not
a measured zero rate.

## 3. Decision policy

### Defaults

- Significance level: `alpha = 0.05`.
- Confidence level: `1 - alpha = 0.95` (95%).
- Primary test: two-sided.
- Planned power: 80%.
- Minimum detectable effect: pre-specified before data collection.
- Stopping rule: no optional stopping. Planned end time or sample size must be
  reached before a confirmatory interpretation. Sequential methods are Version 2.

A one-sided test is not a Version 1 default. It requires pre-registration before
outcome inspection, a declared direction, and a documented amendment to this
specification.

### MDE definition

Every analysis must define:

| Field | Allowed value |
|---|---|
| `mde_type` | `absolute` or `relative` |
| `mde_value` | Finite numeric value greater than zero |
| `mde_direction` | `higher`, `lower`, or `either` |
| Metric scale and unit | Explicit conversion-rate scale (proportion or percentage points) and unit |

The absolute effect is:

```text
absolute_effect = p_treatment - p_control
```

For `mde_type = absolute`, compare the effect magnitude on the declared absolute
scale. For descriptive reporting, when `p_control > 0`, calculate:

```text
relative_lift = (p_treatment - p_control) / p_control
```

Relative MDE is never compared with an absolute effect. Version 1 uses an absolute
MDE for all confirmatory practical-significance decisions. Relative lift may be
displayed descriptively when defined, but relative-MDE decisions are deferred to
Version 2 unless Fieller-based intervals are explicitly implemented, tested, and
documented in a later version. If `p_control = 0`, relative lift and all
relative-MDE practical claims are unavailable.

Two separate questions must be reported:

1. **Observed practical magnitude:** Does the full-precision point estimate reach the
   applicable MDE in the declared direction?
2. **Evidence of practical benefit:** Does the confidence interval support an effect
   at least as large as the applicable MDE in the declared direction?

A strong practical-benefit claim requires both questions to be satisfied. A point
estimate alone is insufficient when the interval is highly uncertain.

For Version 1 absolute MDE point-estimate support, apply these exact rules:

- `higher`: `absolute_effect >= mde_value`
- `lower`: `absolute_effect <= -mde_value`
- `either`: `abs(absolute_effect) >= mde_value`

For interval support of the MDE, use the full-precision Newcombe interval. For
`mde_direction = higher`, its lower bound must be at least `mde_value`; for
`lower`, its upper bound must be at most `-mde_value`; for `either`, the interval
must lie entirely at or beyond either `+mde_value` or `-mde_value`. These rules
apply on the absolute scale. Version 1 does not use a relative-MDE confidence interval for a confirmatory
decision. A future Version 2 Fieller implementation would need to define, test, and
document the ratio confidence set before enabling relative-MDE decisions.

### Data-quality tolerances

The default exclusion tolerance is **5% per arm**. It is a configurable policy
value that must be recorded before analysis and must not be changed after viewing
results.

For each arm, report:

```text
exclusion_rate = excluded_records / records_received
```

`records_received` is the number of raw input records assigned to that arm before
metric-eligibility filtering. Duplicate records remain in this raw denominator and
are reported separately; any duplicate randomization unit blocks the analysis.
If `records_received = 0` for either arm, the exclusion rate is unavailable and the
analysis is blocked because the metric is not estimable.

The analysis is blocked when exclusion rate exceeds 5% in either arm. It is also
blocked when missingness or exclusions are materially different between arms. The
material-difference threshold must be pre-specified; the Version 1 default is an
absolute difference greater than 5 percentage points in either arm. Report counts
and rates for every exclusion category and the reason for every exclusion.

Missing and invalid records are excluded from metric calculations but are never
silently discarded. Invalid records include non-finite outcomes, invalid timestamps,
timezone-naive timestamps unless an explicit pre-analysis timezone policy exists,
unknown arms, outcomes outside `{0, 1}`, records outside the time window, and
structurally malformed records. They may be excluded only when the data-quality
gate permits analysis.

### Sample-ratio mismatch (SRM)

The expected allocation ratio must be pre-specified. For any expected allocation:

- For SRM, `n_control` and `n_treatment` are the unique randomization-unit
  assignment counts before outcome eligibility, missingness, or metric filtering.
  SRM is evaluated on assignment data, not only on units with valid outcomes.
- Report expected and observed allocation by arm.
- Define observed allocation as the treatment share
  `n_treatment / (n_control + n_treatment)` and expected allocation as the
  corresponding pre-specified share.
- Define allocation deviation as
  `abs(observed_treatment_share - expected_treatment_share)`.
- Report the chi-square goodness-of-fit statistic and p-value against the expected
  ratio.
- Show an SRM warning when `allocation_deviation > 0.05`; this threshold applies to
  every expected allocation ratio, not only 1:1.
- Treat SRM as a blocking data-quality failure only when `p_srm < 0.001`.

An **SRM warning** is not automatically blocking; it sets reliability to
`review_recommended` and permits descriptive/confirmatory output if all other gates
pass. A **blocking SRM failure** permits descriptive diagnostics but sets analysis
status to `blocked`, reliability to `blocked`, and verdict to `cannot_analyze`; it
issues no confirmatory verdict.
ExperimentLens must not silently continue as if the assignment mechanism were valid.

### Reliability audit

The public analysis result includes a deterministic reliability audit. Its
typed findings use the categories `structure`, `duplicate_assignment`,
`cross_group_contamination`, `srm`, `missingness`, `exclusion_rate`, `power`,
`multiple_testing`, `peeking`, `preregistration`, and `stopping_rule`, with
`info`, `warning`, or `blocking` severity. Findings include stable reason
codes, evidence, remediation, and a blocking flag.

The audit reports duplicate assignments and confirmatory cross-group
contamination as blocking. Exclusion tolerance and unequal-exclusion gates use
the configured thresholds. Underpowered and unavailable power planning remain
distinct review findings. SRM uses assignment counts: deviation above the
warning threshold is review-recommended, while p-values below the blocking
threshold are blocking.

Version 1 audits multiplicity and stopping risks without adding multiplicity
corrections or sequential inference. One pre-registered primary hypothesis with
a fixed stopping rule and no unauthorized interim looks is acceptable. Multiple
confirmatory hypotheses without a declared adjustment, missing
pre-registration, unsupported stopping rules, optional stopping, and
unauthorized interim looks are blocking. Exploratory multiplicity or interim
looks are warnings and cannot produce a confirmatory verdict.

## 4. Mandatory analysis order

The implementation must execute and record these steps in order:

1. Validate experiment structure.
2. Validate duplicate/randomization-unit integrity.
3. Validate missing and invalid records.
4. Run allocation/SRM checks.
5. Determine estimability and sample sufficiency.
6. Select the statistical method.
7. Compute effects, intervals, and p-values.
8. Assign analysis status, evidence/design status, reliability, and verdict.

A blocking data-quality failure always takes precedence over statistical significance.

## 5. Statistical methods

### Expected-cell rule and method selection

For the binary 2x2 table:

```text
                 Success  Failure
Control             x_c    n_c-x_c
Treatment           x_t    n_t-x_t
```

Compute expected cell counts under the null of equal conversion rates. Use the
pooled two-proportion z-test **only when all four expected cell counts are at least
5**. Otherwise use the two-sided Fisher's exact test. Always report the selected
method and method-selection reason.

### Two-proportion z-test

Test `H0: p_treatment - p_control = 0` against the two-sided alternative.

```text
p_pool = (x_c + x_t) / (n_c + n_t)
SE_null = sqrt(p_pool * (1 - p_pool) * (1/n_c + 1/n_t))
z = (p_treatment - p_control) / SE_null
p_value = 2 * (1 - Phi(abs(z)))
```

The z-test is not used when its standard error is zero or any expected cell is
below 5. Such tables use Fisher's exact test unless the table is not estimable.

### Fisher's exact test

Use the two-sided Fisher p-value for any table with an expected cell count below 5,
including degenerate tables where the normal approximation is unsuitable. Report
the exact-test method and trigger. Effect estimates and confidence intervals remain
separately reported.

### Confidence intervals

Report 95% Wilson score intervals for each arm's individual conversion rate. Report
a 95% Newcombe interval for the absolute difference `p_treatment - p_control`,
formed from the two independent Wilson intervals. Use full precision for decisions;
round only for display.

## 6. Binary edge cases

| Condition | Required behavior |
|---|---|
| Zero eligible units in either arm | Metric is undefined; `analysis_status = blocked`, `verdict = cannot_analyze`. Never display zero as a measured rate. |
| Both groups have zero conversions | Rates are estimable as zero. Report descriptive rates and effects; use Fisher's exact test because expected success cells are below 5. Do not hard-code a z-score or verdict. |
| Both groups have 100% conversions | Rates are estimable as one. Report descriptive rates and effects; use Fisher's exact test because expected failure cells are below 5. Do not hard-code a z-score or verdict. |
| One group has zero conversions | Report estimable rates, absolute lift, and relative lift when control rate is nonzero; use Fisher if any expected cell is below 5. |
| One group has 100% conversions | Report estimable rates and effects; use Fisher if any expected cell is below 5. |
| Identical rates | Effect is zero; compute the selected method's p-value and interval rather than hard-coding a verdict. |
| Control rate is zero | Relative lift is undefined. Report absolute lift and use absolute MDE for practical interpretation. |

If a selected method cannot produce an estimable p-value or interval, retain
descriptive rates/effects where possible and return `cannot_analyze`; never substitute
a fabricated zero statistic or favorable verdict.

## 7. Power, sample sufficiency, and evidence

The analysis plan must record required sample size calculated from the selected
binary-test design, alpha, two-sided tail, planned power, expected allocation,
baseline conversion rate, and MDE. Sample sufficiency is a design status:

- `adequately_powered`: required sample size is met.
- `underpowered`: either arm is below its pre-registered requirement.

For the default 1:1 design, calculate the initial required sample size per arm with
the normal-approximation planning formula:

```text
p_bar = (p_control + p_treatment_at_MDE) / 2
n_per_arm = ceil(
  (z_(1-alpha/2) * sqrt(2 * p_bar * (1-p_bar))
   + z_power * sqrt(
       p_control * (1-p_control)
       + p_treatment_at_MDE * (1-p_treatment_at_MDE)
     ))^2
  / (p_treatment_at_MDE - p_control)^2
)
```

For a non-1:1 allocation, search integer pairs `(n_control, n_treatment)` that
honor the pre-specified allocation ratio and select the smallest pair whose planned
two-sided power is at least the target power. Record the planning algorithm,
baseline, MDE alternative, allocation, alpha, power, and resulting per-arm
requirements. If the planned counts produce sparse expected cells, issue a planning
warning and validate achieved power by the Version 1 simulation-validation procedure;
do not silently claim that the normal approximation is exact.

Meeting planned sample size does not guarantee a valid result; design status does not
override data-quality, assignment, or method assumptions. Failing to meet it does
not make descriptive or estimable statistical calculations impossible.

When underpowered but otherwise estimable, calculate and display the result, mark it
clearly as underpowered, do not interpret non-significance as equality, and do not
issue an unqualified business recommendation. Use `insufficient_evidence` when the
pre-specified evidence policy requires a stronger conclusion. An implementation may
also report `evidence_status = insufficient_evidence` alongside an `inconclusive`
verdict when it displays the statistical result but cannot support a stronger claim.

An underpowered experiment may still receive `positive_result` or `negative_result`
if all pre-specified significance and absolute practical-effect interval rules are
satisfied. It remains marked `underpowered` and must not receive an unqualified
business recommendation.

## 8. Secondary metrics

Exactly one primary metric receives the confirmatory verdict. Version 1 secondary
metrics are descriptive by default. Their confidence intervals may be displayed.
Their p-values must not be presented as confirmatory winner claims unless multiplicity
control was pre-specified.

If formal secondary testing is later supported, require an explicit multiplicity
method such as Holm or Benjamini-Hochberg and record the method and adjusted
thresholds.

## 9. Analysis status, reliability, and verdict

These are separate fields:

```text
analysis_status:
  confirmatory
  exploratory
  blocked

design_status:
  adequately_powered
  underpowered
  unavailable

evidence_status:
  significant
  non_significant
  insufficient_evidence
  unavailable

reliability:
  acceptable
  review_recommended
  blocked

verdict:
  positive_result
  negative_result
  inconclusive
  statistically_significant_practically_weak
  statistically_significant_practical_impact_uncertain
  insufficient_evidence
  cannot_analyze
```

For `analysis_status = exploratory`, `verdict` is `null` (not applicable) and any
descriptive interpretation must be labeled exploratory. The enumerated verdicts
apply only to confirmatory analyses; an exploratory p-value must not be rendered as
a confirmatory winner claim.

Unregistered or post-hoc analyses are `exploratory` and must not receive a
confirmatory verdict. Blocking data-quality, structure, duplicate, or SRM failures
produce `analysis_status = blocked`, `reliability = blocked`, and
`verdict = cannot_analyze`; descriptive diagnostics may still be shown.

### Warning severity

Every warning has one of these severities:

- `info`: recorded context with no reliability concern.
- `warning`: reliability review is recommended, but descriptive and confirmatory
  output may be shown if all other gates pass.
- `blocking`: confirmatory interpretation is prohibited and the analysis is blocked.

An SRM warning is severity `warning`; an SRM blocking failure is severity
`blocking`. Missingness/exclusion tolerance failures, duplicate units, invalid
structure, and non-estimable metrics are also `blocking`. Underpowered design is a
`warning` when results are estimable, unless the pre-specified evidence policy
requires `insufficient_evidence`.

### Machine-readable values and user-facing labels

| Machine value | User-facing label |
|---|---|
| `confirmatory` | Confirmatory |
| `exploratory` | Exploratory |
| `blocked` | Blocked |
| `adequately_powered` | Adequately powered |
| `underpowered` | Underpowered |
| `unavailable` | Unavailable |
| `acceptable` | Acceptable |
| `review_recommended` | Review recommended |
| `significant` | Statistically significant |
| `non_significant` | Not statistically significant |
| `insufficient_evidence` | Insufficient evidence |
| `positive_result` | Positive result |
| `negative_result` | Negative result |
| `inconclusive` | Inconclusive |
| `statistically_significant_practically_weak` | Statistically significant, practically weak |
| `statistically_significant_practical_impact_uncertain` | Statistically significant, practical impact uncertain |
| `cannot_analyze` | Cannot analyze |

`unavailable` is interpreted according to the field where it appears, such as an
unavailable design status, evidence status, or other field that permits that value.

### Mandatory verdict policy

1. Validate design and data quality.
2. If duplicate units, invalid group structure, blocking SRM, or another blocking
   failure exists, provide diagnostics where possible, block the analysis, and issue
   no confirmatory verdict.
3. If not pre-registered, set `analysis_status = exploratory` and do not issue a
   confirmatory verdict.
4. Determine whether both arms have estimable metrics.
5. Determine powered/underpowered design status.
6. Select the method using expected cell counts.
7. Compute full-precision effects, intervals, statistics, and p-values.
8. If `p >= alpha`, use `inconclusive`; if underpowered, also report
   `evidence_status = insufficient_evidence` and the underpowered design status.
9. If `p < alpha`:
   - use `positive_result` when treatment direction and the relevant practical
     threshold are supported by the confidence interval;
   - use `negative_result` when control direction and the relevant practical
     threshold are supported;
   - use `statistically_significant_practically_weak` when significance holds but
     the point estimate is smaller than the applicable MDE;
   - use `statistically_significant_practical_impact_uncertain` when the point
     estimate reaches the MDE but the confidence interval does not support an effect
     at least that large.
10. Report all assumptions, warnings, limitations, and reproducibility metadata.

Version 1's confirmatory practical threshold is always the absolute MDE. A relative
MDE is never silently substituted or used for a Version 1 verdict. A favorable
direction with insufficient evidence is not a winner claim.

### Decision table

| Condition | Analysis status | Reliability | Verdict |
|---|---|---|---|
| Blocking structure, duplicate, data-quality, or SRM failure | `blocked` | `blocked` | `cannot_analyze` |
| Non-estimable metric or unavailable selected method | `blocked` | `blocked` | `cannot_analyze` |
| Valid but underpowered; policy requires stronger evidence | `confirmatory` | `acceptable` or `review_recommended` | `insufficient_evidence` |
| Valid, estimable, `p >= alpha` | `confirmatory` | as assessed | `inconclusive` |
| Significant, favorable, practical threshold supported by interval | `confirmatory` | as assessed | `positive_result` |
| Significant, unfavorable, practical threshold supported by interval | `confirmatory` | as assessed | `negative_result` |
| Significant, point estimate below MDE | `confirmatory` | as assessed | `statistically_significant_practically_weak` |
| Significant, point estimate reaches MDE but interval does not support that magnitude | `confirmatory` | as assessed | `statistically_significant_practical_impact_uncertain` |

Statistical significance does not by itself prove causality. A causal interpretation
requires valid random assignment, consistent treatment exposure, valid outcome
measurement, acceptable data quality, and no material experiment contamination.
ExperimentLens cannot prove all causal assumptions from summary data alone.

## 10. Required result record

Every result must include:

- Experiment identifier; start and end timestamps; UTC normalization status.
- Control and treatment labels; randomization unit.
- Expected and observed allocation; allocation deviation; SRM statistic and p-value;
  SRM warning/block reason.
- Metric name, binary type, unit, direction, and primary/secondary status.
- `mde_type`, `mde_value`, metric scale/unit, and `mde_direction`.
- Records received, eligible, valid, excluded, missing, invalid, and duplicate counts
  by arm; exclusion rates and reason for every exclusion category.
- Method and method-selection reason.
- Conversion rates, effect estimate, absolute lift, and relative lift when defined.
- Wilson intervals, Newcombe interval, test statistic, and full-precision p-value.
- Alpha, tail, confidence level, planned power, required sample size, design status,
  and observed power where supported.
- Stopping-rule status, pre-registration status, analysis status, reliability, verdict,
  evidence status, warning severity and messages, limitations, and reasons for any
  blocked or insufficient outcome. Exploratory records must contain `verdict = null`.
- Reproducibility information: input-data identity/version, software configuration,
  specification version, and any random seed used by future stochastic methods.

## 11. Reproducibility and validation

Statistical outputs must be reproducible from the recorded input-data identity,
configuration, specification version, and deterministic method implementation.
Version 1 must validate formulas and decision boundaries with trusted reference
fixtures and simulation-based checks covering null behavior, power, allocation
imbalance, sparse tables, degenerate tables, missingness, and SRM failures.

Simulation validation does not replace mathematical definitions or data-quality
checks; it verifies that the implementation behaves as specified.

## 12. Version 1 acceptance checklist

This specification is complete only if it defines:

- Every input and output field.
- Every formula and statistical method.
- Every assumption and causal limitation.
- Every threshold, including alpha, power, MDE, exclusion, SRM, and expected cells.
- Every rounding and timestamp rule.
- Every invalid-data, duplicate, missingness, and degenerate-table behavior.
- Every analysis status, reliability state, evidence status, warning severity, and verdict.
- Every reproducibility and simulation-validation requirement.

No calculation, displayed statistic, warning, status, or verdict may be added to
ExperimentLens unless its definition, assumptions, thresholds, rounding rule, and
edge-case behavior are defined here or in a versioned amendment.

## 13. Terminology glossary

| Term | Definition |
|---|---|
| Arm/group | One mutually exclusive experience, control or treatment. |
| Eligible unit | A randomization unit with one valid in-window binary outcome. |
| Conversion rate | Binary successes divided by eligible units. |
| Absolute lift | `p_treatment - p_control`, on the declared absolute scale. |
| Relative lift | Absolute lift divided by control rate when control rate is nonzero. |
| MDE | Pre-specified minimum effect considered practically important. |
| p-value | Probability under the null model of a result at least as extreme as observed. |
| Significance level | Planned Type I error rate, default 0.05. |
| Confidence interval | Interval procedure with 95% nominal coverage under its assumptions. |
| SRM | Sample-ratio mismatch between observed and expected allocation. |
| Underpowered | Required pre-registered sample size is not met. |
| Exploratory | Unregistered or post-hoc analysis without a confirmatory verdict. |
| Blocked | A structural or data-quality failure prevents confirmatory interpretation. |
| Practically weak | Significant, but point-estimate magnitude is below the applicable MDE. |
| Practical impact uncertain | Point estimate reaches MDE, but its interval does not support that magnitude. |
