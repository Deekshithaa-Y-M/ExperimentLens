# Phase 4 independent verification

Status: **complete for the implemented Version 1 statistical core**. This phase
added verification only; no production feature or statistical-contract changes
were required.

## Reference methods and tolerances

- Two-proportion z-tests were recomputed independently with pooled variance and
  `scipy.stats.norm.sf`.
- Fisher's exact p-values were compared with `scipy.stats.fisher_exact`.
- Wilson intervals were recomputed independently with `scipy.stats.norm.ppf`;
  Newcombe intervals were compared as the difference of those independent arm
  intervals.
- Planned power was recomputed from independent normal CDF/SF evaluations using
  `scipy.stats.norm`.
- Stable floating-point comparisons use explicit `rel=1e-12, abs=1e-14`.
  Probability fixtures use the same policy; categorical and integer outputs use
  exact equality. Simulation proportions use stated acceptance ranges.

## Verification coverage

The new tests are in:

- `backend/tests/test_reference_comparisons.py`
- `backend/tests/test_known_values.py`
- `backend/tests/test_boundary_behavior.py`
- `backend/tests/test_simulation_validation.py`

They cover known conversion/lift, z-test, Fisher, Wilson, Newcombe, power,
sample-size, non-1:1 allocation, sparse and degenerate tables, zero eligible
units, alpha equality and near-boundaries, MDE equality and direction, rounded
display values, data-quality/SRM precedence, and reproducibility.

## Simulation parameters and actual results

All simulations use NumPy `default_rng` with fixed seeds.

| Check | Seed | Replications | Parameters | Actual result | Threshold |
|---|---:|---:|---|---:|---|
| Null false-positive rate | 20261031 | 2,000 | n=200/arm, p=0.20/0.20, alpha=.05 | 112 significant; 0.056 | 0.02–0.08 |
| Null Wilson coverage | 20261031 | 2,000 | n=200, true p=.20, 95% interval | 1,914 covered; 0.957 | 0.90–0.99 |
| Null SRM false detections | 20261031 | 2,000 | assignments 200/200, expected share=.50, p<.001 | 0; 0.000 | exactly 0 in this check |
| Known-effect power | 20261101 | 2,000 | n=200/arm, p=.20/.30, alpha=.05 | 1,271 significant; 0.6355 | 0.45–0.75 |
| Allocation SRM detection | 20261101 | 2,000 | assignments 200/300, expected share=.50, p<.001 | 2,000 detected; 1.000 | at least 0.95 |
| Sparse/degenerate execution | 20261102 | 500 | n=20/arm, p=.01/.01 | 500 Fisher results with p-values | all executions valid |

The null simulation was run twice with seed `20261031`; the complete result
dictionary was identical.

## Discrepancies and fixes

The first test draft contained three incorrect hand-entered expected values and
an SRM simulation imbalance that was too small for the requested `p < .001`
detection threshold. These were test-fixture errors identified by execution,
not production discrepancies. The values were replaced with the actual
hand-checkable calculations and the simulation assignment imbalance was changed
to 200/300. No production fix was made.

## Validation

- `$env:PYTHONPATH='backend\src'; python -m pytest backend\tests -q`: **46 passed**
- `python -m ruff check backend\src backend\tests`: **passed**
- `python -m mypy backend\src`: **passed**

The JavaScript calculator and browser/manual artifacts were intentionally not
changed. Remaining limitation: the simulation checks are finite-sample
validation checks rather than a proof of behavior outside the tested parameter
ranges; future statistical-contract changes require new reference fixtures.
