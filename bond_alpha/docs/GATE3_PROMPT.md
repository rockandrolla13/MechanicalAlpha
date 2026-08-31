# Gate 3 Prompt

## Frozen-Calibration Rule

Gate 3 must load:

```text
models/frozen/<calibration_id>/
```

and must not refit or mutate:

- liquidity mapping;
- activity model;
- Hawkes masses or decays;
- SynthCity model;
- empirical fallback pools;
- fair-value model;
- OU parameters;
- price-noise model;
- effect-neutralization model;
- planted-effect parameters;
- train-derived thresholds;
- category mappings;
- plotting bins;
- plotting axis policies;
- validation metric definitions.

Before running Gate 3:

1. verify the frozen calibration checksums;
2. verify the source-data fingerprint;
3. verify the resolved configuration hash;
4. verify the software environment or report deviations;
5. record the frozen calibration ID in every output manifest.

Any desired model change invalidates the current Gate 3 run. Create a new Gate 2.5 calibration version rather than changing the frozen bundle.

## Gate 3 Locked Validation Visualization

Run the visualization and metric code frozen at Gate 2.5 without changing:

- metric definitions;
- horizons;
- bins;
- axis ranges;
- control groups;
- bootstrap design;
- significance level;
- multiplicity correction;
- effect-recovery tolerances.

Generate:

```text
reports/gate3/index.html
reports/gate3/gate3_summary.md
reports/gate3/gate3_summary.json
reports/gate3/plot_data/
reports/gate3/figures/
```

Required Gate 3 figures:

1. controlled versus null large-print event-study curve;
2. reversal coefficient by horizon and seed;
3. configured versus recovered reversal magnitude;
4. sign-continuation probability by gap bucket;
5. same-side versus opposite-side hazard ratio;
6. configured versus recovered Hawkes sign asymmetry;
7. leader-to-follower response by horizon;
8. follower-to-leader negative control;
9. cross-issuer negative control;
10. configured versus recovered lead-lag magnitude;
11. forest plot of all recovered coefficients by seed;
12. controlled-minus-null paired differences;
13. estimator bias by seed;
14. estimator RMSE by effect;
15. confidence-interval coverage across seeds;
16. detection rate across seeds;
17. factor performance as a function of bond liquidity;
18. factor performance as a function of event count;
19. overlap and contamination diagnostics;
20. any failed gate, displayed rather than suppressed.

For each effect, display:

```text
configured structural truth
oracle recovered value
public-data recovered value
matched-null value
standard error or interval
number of eligible events
number of issuers
number of bonds
simulation seed
```

Use issuer-day block bootstrap or another predeclared clustered procedure. Do not use row-level iid standard errors.

All figures must have machine-readable Parquet backing tables.

The report must clearly distinguish:

```text
structural parameter
oracle state recovery
observable-data estimator recovery
economic detectability
statistical significance
```

Do not represent a statistically significant coefficient as accurate magnitude recovery when it is materially biased.

## Post-Gate 3 Approval Gate

Gate 3 should conclude with an immutable decision artifact:

```text
reports/gate3/GATE3_DECISION.json
```

It should have this structure:

```json
{
  "calibration_id": "calibration-v1.0.0",
  "gate3_run_id": "...",
  "decision": "PASS | FAIL | PASS_WITH_WARNINGS",
  "reversal": {
    "sign_success_rate": 1.0,
    "median_relative_error": 0.14,
    "null_fraction": 0.08,
    "passed": true
  },
  "sign_persistence": {
    "sign_success_rate": 0.8,
    "median_relative_error": 0.21,
    "null_fraction": 0.11,
    "passed": true
  },
  "leadlag": {
    "sign_success_rate": 1.0,
    "median_relative_error": 0.18,
    "reverse_control_fraction": 0.06,
    "cross_issuer_control_fraction": 0.04,
    "passed": true
  },
  "fatal_failures": [],
  "warnings": [],
  "approved_for_gate4": true
}
```

Gate 4 should refuse to start unless:

```text
approved_for_gate4 = true
```

## Reproducibility Hardening That Matters Most

The most important additions are not the charts themselves. They are the controls around them.

Save the data behind every plot. A PNG cannot be audited easily. Each figure should have:

```text
figure.png
figure.svg
figure_data.parquet
figure_metadata.json
```

For example:

```text
large_print_reversal_by_horizon.png
large_print_reversal_by_horizon.svg
large_print_reversal_by_horizon.parquet
large_print_reversal_by_horizon.metadata.json
```

Freeze binning and plotting rules. Bins must be learned from training data and then frozen:

- notional bins;
- interarrival bins;
- liquidity deciles;
- intraday buckets;
- large-print thresholds;
- effect horizons;
- axis limits;
- tail cutoffs.

Otherwise two reports can look different simply because their bins changed.

Use ensemble bands, not one attractive seed. Every important plot should show the median across seeds and a Monte Carlo envelope. A single-seed chart is useful for debugging but insufficient for approval.

Separate numerical and visual regression testing. Numerical plot-data tables are the primary reproducibility target. Pixel-level image comparison can be brittle across operating systems and font-rendering versions.

Use:

- exact hash comparison for plot-data tables;
- tolerance-based image comparison in the pinned reference environment.

Keep failed plots. The report generator must not omit a figure because a metric failed or returned an unexpected sign. Generate a visible failure panel and record the failure in the decision JSON.

Version every recalibration. A failed Gate 3 followed by a model change should produce:

```text
calibration-v1.1.0
```

or:

```text
calibration-v2.0.0
```

The original calibration and its failed Gate 3 report remain untouched. This creates a complete research audit trail rather than a sequence of overwritten experiments.

The immediate next step is Gate 2.5, not Gate 3. It produces the calibrated visual report and the frozen bundle that Gate 3 will evaluate unchanged.

## Gate 3: Medium-Scale Calibration And Adversarial Validation

Run:

- 100 synthetic bonds;
- approximately 20-30 issuers;
- 100 trading sessions;
- five independent seeds;
- calibrated_realism;
- controlled_all;
- controlled_null;
- reversal_only;
- sign_only;
- leadlag_only.

Use common random-number streams across matched scenarios wherever possible.

Validate against the held-out real-data period:

1. Bond-level trades per day.
2. Zero-trade-day frequency.
3. Intraday activity profile.
4. Interarrival-time distributions.
5. Side balance and run lengths.
6. Notional distributions, including the upper tail.
7. Interdealer frequency.
8. Transaction-concession distributions.
9. Residual price volatility and autocorrelation.
10. Issuer-level co-movement.
11. Own-print response curves.
12. Leader-to-follower response curves.

Run observable-data positive-control tests without using truth columns:

- large-print reversal;
- sign persistence;
- leader-to-follower lead-lag;
- follower-to-leader negative control;
- cross-issuer negative control.

Also run oracle accounting tests using the hidden truth ledger.

Do not tune acceptance thresholds after seeing results. Do not simply increase planted-effect magnitudes to force detection.

For failed recovery, diagnose:

- low statistical power;
- sparse follower activity;
- event overlap;
- side measurement error;
- excessive observation noise;
- incorrect residualization;
- effect leakage into the nuisance model;
- Hawkes instability;
- mark-model distortion.

Create:

- `reports/medium_validation.md`
- `reports/fidelity/medium_summary.md`
- `reports/recovery_across_seeds.csv`
- `reports/null_controls_across_seeds.csv`
- `reports/model_risk_findings.md`

Only declare Gate 3 passed if:

- the intended effect has the correct sign in at least four of five seeds;
- median recovered magnitude is within 25% of configured truth, or a properly constructed interval contains the truth;
- the matched null effect is below 20% of the controlled magnitude;
- reverse-direction and cross-issuer controls are near zero;
- no data leakage or truth-column leakage is detected.
