# Gate 4 and Alpha Factory v1: full-scale generation, blinded alpha development, and truth recovery

You are a senior quantitative developer, corporate-bond market-microstructure researcher, and reproducible-research engineer. Work directly in the current repository. Read the existing simulator master prompt, Gate 1–3 reports, the frozen calibration bundle, and the repository README before making changes.

Do not return only a plan. Implement the required package code, configuration, tests, commands, reports, and smoke/full runs that the available environment permits. Be explicit about anything not executed.

## 1. Objective

Complete two connected workstreams:

1. **Gate 4 production-scale simulation**
   - 500 synthetic corporate bonds;
   - approximately 100 issuers, preserving the frozen issuer-family construction;
   - 756 trading sessions;
   - calibrated-realism, controlled, null, and single-effect scenarios;
   - deterministic, resumable, streamed Parquet output;
   - complete public/truth separation;
   - full structural, fidelity, recovery, and reproducibility reports.

2. **Alpha Factory v1**
   - build production-like alpha features using only public synthetic observables;
   - freeze feature, label, split, model-selection, and evaluation specifications before inspecting Gate 4 outcomes;
   - evaluate the frozen alpha pipeline on Gate 4 as an out-of-sample test;
   - unblind only after the alpha specification is frozen;
   - compare public-data estimates with structural truth and matched nulls;
   - produce RFQ-ready alpha outputs without prematurely turning every predictive effect into an outright trading strategy.

The mandatory alpha families are:

1. large-print reversal;
2. sign/flow persistence;
3. liquid-leader-to-illiquid-follower issuer lead-lag;
4. issuer-relative-value mean reversion;
5. a transparent composite built only after the individual alphas pass.

## 2. Hard preconditions

Before Gate 4 starts, verify:

```text
reports/gate3/GATE3_DECISION.json exists
approved_for_gate4 == true
one frozen calibration bundle exists
all frozen-bundle checksums pass
source-data fingerprint matches
resolved configuration hash matches
Git commit and dirty state are recorded
software-environment differences are recorded
```

If `approved_for_gate4` is false or missing, do not represent the full run as a scientific validation. A scale-only engineering run may be executed under an explicit `research_only_scale_test` flag, but it must not be used to approve alphas.

Gate 4 must not refit or mutate:

```text
liquidity mapping
activity model
Hawkes parameters or edge graph
mark generator or empirical fallback pools
fair-value model
OU parameters
transaction-concession model
impact-neutralization model
planted-effect parameters
training-derived thresholds
category mappings
plot bins or axis policies
metric definitions
recovery tolerances
```

Any change requires a new Gate 2.5 calibration version and a new Gate 3 decision.

## 3. Blinded research design

Gate 4 is the final synthetic out-of-sample test. It may be generated before alpha development finishes, but its public outputs must be quarantined until the alpha specification is frozen.

Use this separation:

```text
Alpha development data:
    Gate 3 public synthetic data only, plus real training/validation data where permitted.

Alpha specification freeze:
    feature definitions, labels, horizons, stale-price rules, splits,
    model classes, hyperparameter grids, costs, metrics, plots, and gates.

Gate 4 public evaluation:
    frozen alpha code applied without tuning.

Truth unblinding:
    separate validation command after the Gate 4 public predictions and reports
    have immutable hashes.
```

The alpha-development process must not access:

```text
data/synthetic_truth/
parameter_truth.json
realized_truth.json
latent fair values
latent mids
Hawkes parentage
planted-effect flags
source leader event IDs
truth-derived effect half-lives or amplitudes
```

Implement a runtime guard and tests that fail if alpha feature/model code reads a truth path or truth column.

## 4. Gate 4 run matrix

### 4.1 Canonical full run

Generate all scenarios for one canonical master seed:

```text
calibrated_realism
controlled_all
controlled_null
reversal_only
sign_only
leadlag_only
```

Use:

```text
500 bonds
756 sessions
frozen issuer structure
frozen calibration ID
canonical seed from the frozen configuration
```

Use common random-number streams across matched scenarios wherever mathematically possible.

### 4.2 Scale-robustness runs

Because Gate 3 already provides five-seed medium-scale recovery, do not multiply every full scenario unnecessarily. Add two additional full-scale seeds for:

```text
controlled_all
controlled_null
```

This gives three full-scale controlled/null pairs while keeping compute and storage bounded. Make the extra seeds configurable.

### 4.3 Streaming and resumability

Simulate each scenario sequentially through time so fair-value, OU, and impact states remain continuous. Parallelize only across independent scenarios or seeds unless deterministic state handoff is implemented and tested.

Write monthly Zstandard-compressed Parquet partitions. Maintain checkpoint state at session boundaries:

```text
current session
factor state
OU state
impact states
lead-lag state
random-generator states
output partition checksums
```

A resumed run must produce the same canonical content hashes as an uninterrupted run.

Do not silently truncate Hawkes clusters, drop invalid mark rows, or skip failed sessions. Fail with an actionable diagnostic.

## 5. Gate 4 output contract

Create:

```text
runs/gate4/<gate4_run_id>/
    resolved_config.yaml
    gate3_decision.json
    frozen_calibration_reference.json
    source_fingerprint.json
    software_environment.json
    seed_manifest.json
    run_manifest.json
    progress/
    metrics/
    logs/
    checksums.sha256

data/synthetic/gate4/<gate4_run_id>/scenario=<scenario>/seed=<seed>/
    bonds.parquet
    trades/year=YYYY/month=MM/part-*.parquet
    manifest.json

data/synthetic_truth/gate4/<gate4_run_id>/scenario=<scenario>/seed=<seed>/
    event_truth/year=YYYY/month=MM/part-*.parquet
    parameter_truth.json
    realized_truth.json
    manifest.json

reports/gate4/<gate4_run_id>/
    index.html
    summary.md
    summary.json
    plot_data/
    figures/
    fidelity/
    recovery/
    reproducibility/
```

The public dataset must contain no truth fields or source identifiers.

## 6. Gate 4 validation

Run all frozen structural and calibration gates, including:

```text
exactly 500 synthetic bonds
exactly 756 sessions
valid issuer leader/follower assignments
no duplicate event IDs
no events outside sessions
valid sides and categories
positive finite notionals and prices
no NaN/Inf public values
Hawkes spectral radius below the frozen maximum
positive immigrant baselines
no cluster safety-cap hits
price-component accounting identity
public/truth physical separation
same-seed deterministic canonical hashes
resume-versus-uninterrupted hash equality
median events/day in [1.90, 2.10]
p10 events/day in [0.36, 0.44]
```

Re-run the frozen visualization suite at full scale. Save Parquet data behind every figure. Do not change bins or axes after viewing results.

## 7. Alpha Factory package

Create a separate package boundary so alpha research cannot accidentally depend on simulator internals:

```text
src/bondalpha/
    __init__.py
    cli.py
    config.py
    contracts.py
    access_guard.py
    datasets.py
    labels.py
    splits.py
    thresholds.py
    features/
        common.py
        reversal.py
        flow_persistence.py
        leader_follower.py
        relative_value.py
        controls.py
    models/
        baselines.py
        linear.py
        nonlinear.py
        calibration.py
        composite.py
    evaluation/
        predictive.py
        recovery.py
        economic.py
        nulls.py
        stability.py
        rfq.py
    visualization/
        features.py
        coefficients.py
        calibration.py
        pnl.py
        recovery.py
        report.py
    freeze.py
    unblind.py

configs/alphas/
    base.yaml
    reversal.yaml
    flow_persistence.yaml
    leader_follower.yaml
    relative_value.yaml
    composite.yaml
    null_controls.yaml

tests/alpha/
```

Do not import from `bondsim.truth` or any simulator-only latent-state module.

## 8. Public alpha data contract

The alpha package may read only production-like fields such as:

```text
event_id
timestamp_utc
session_date
synthetic_bond_id
synthetic_issuer_id
side
notional
price
is_interdealer
trade_type
venue_bucket
reporting_delay_ms
currency
public bond metadata
public quotes or public fair-value fields only if explicitly present in the target pipeline
```

Use one documented side convention. If `side = +1` means customer buy, state that a positive clean-price forecast represents adverse selection for a dealer selling to the customer.

All as-of joins must be backward-looking. Add tests for future leakage, timestamp ties, stale data, and reporting-delay handling.

## 9. Labels

Construct labels without truth data.

### 9.1 Public clean-price proxy

Use the best production-observable route frozen in the alpha specification:

1. as-of midpoint from two-sided quotes, when available;
2. public evaluated fair value available at the decision timestamp;
3. issuer-curve clean-price estimator fit only on past data;
4. robust transaction-based clean-price proxy with side-concession correction and staleness limits.

Do not use a future print to backfill the current midpoint.

### 9.2 Primary horizons

Use predeclared horizons:

```text
30 minutes
2 trading hours
1 trading day
```

A five-day horizon may be included as a secondary RFQ/inventory horizon, but it is not a mandatory positive-control recovery horizon.

### 9.3 Labels

Create:

```text
future_clean_move_points
future_issuer_residual_move_points
future_market_residual_move_points
next_event_side
next_issuer_event_side
future_signed_flow
```

For price alpha:

\[
y_{i,t,h}
=\widetilde P_i(t+h)-\widetilde P_i(t),
\]

and issuer-residual alpha:

\[
y^{res}_{i,t,h}
=y_{i,t,h}-\widehat\beta_i^\top\Delta F_{issuer,market}(t,h).
\]

Record label availability, staleness, interpolation method, and overlap.

## 10. Temporal splitting and inference

Use purged walk-forward splits with an embargo at least as long as the maximum label horizon. Keep issuer-day clusters intact where possible.

For Gate 3 development data:

```text
development folds: earlier dates
validation fold: later dates
alpha specification freeze: after validation
```

Gate 4 is not used for hyperparameter selection.

Use issuer-day clustered or block-bootstrap uncertainty. Do not treat individual events as independent observations.

Apply Holm correction across the predeclared mandatory alpha tests.

## 11. Alpha 1: large-print reversal

Define training-derived, frozen bond- or bucket-level thresholds:

\[
q^{large}_i = Q_{0.90}(q\mid i\text{ or pooled bucket}).
\]

Normalize size:

\[
g(q_e)=\min\left(g_{max},\sqrt{q_e/q_{50,i}}\right).
\]

Create a decayed reversal feature:

\[
x^{rev}_{i,t}
=-\sum_{e\in i:t-W<t_e\le t}
\mathbf 1(q_e\ge q^{large}_i)s_e g(q_e)
\exp[-(t-t_e)/\tau].
\]

Use a small predeclared candidate grid for `tau`, selected on Gate 3 validation only, for example:

```text
30 minutes
2 hours
0.5 trading day
1 trading day
```

Do not read the truth half-life.

Evaluate:

- coefficient and monotonicity versus large-print size;
- response by horizon;
- incremental value beyond ordinary signed flow;
- effect by liquidity decile;
- controlled versus null;
- shuffled-sign control;
- pseudo-large-print threshold control;
- gross and net value.

A successful recovery does not automatically imply a standalone trade. The configured six-cent one-day reversal can be smaller than a 7.5-cent round-trip cost. Report predictive recovery separately from executable economics. Treat it first as an adverse-selection and quote-skew input.

## 12. Alpha 2: sign and flow persistence

This alpha has two distinct outputs:

1. **next-flow probability**, useful for inventory and quote skew;
2. **short-horizon price/adverse-selection forecast**, only if the data support it.

Create features:

\[
OFI_{i,t}^{(w)}=\sum_{e:t-w<t_e\le t}s_e\,g(q_e),
\]

for frozen windows such as 5 minutes, 30 minutes, and 2 hours.

Create an intensity-skew feature from the public fitted event model or recursively computed decayed counts:

\[
x^{flow}_{i,t}
=\log\frac{\widehat\lambda_{i,+}(t)+\epsilon}
{\widehat\lambda_{i,-}(t)+\epsilon}.
\]

Predict:

```text
P(next event side = BUY)
expected signed flow over 30m and 2h
future clean-price move, reported separately
```

Use logistic regression as the primary interpretable baseline. Calibrate probabilities on validation data only.

Negative controls:

```text
signs shuffled within bond-day
same features shifted into the future
unrelated matched bond flow
symmetrized controlled-null scenario
```

Do not call next-side prediction a return alpha unless it has incremental public-data price-prediction value.

## 13. Alpha 3: issuer leader-to-follower lead-lag

Determine each issuer leader from training-period public liquidity only. Freeze the mapping.

Do not hard-code the truth impulse kernel. Use predeclared distributed-lag features based on signed leader prints:

```text
0–30 minutes
30–90 minutes
90–180 minutes
3 hours–1 day
```

For follower `i` and leader `l(i)`:

\[
x^{lead}_{i,t,b}
=\sum_{e\in l(i)}s_e g(q_e)
\mathbf 1(t-t_e\in b).
\]

Control for:

```text
follower own signed flow
issuer common move
sector/market move
liquidity
intraday bucket
recent follower trade indicator
leader/follower activity regime
```

Estimate follower residual-return responses at 30 minutes, 2 hours, and 1 day.

Mandatory controls:

```text
follower-to-leader reverse direction
matched cross-issuer leader
permuted issuer assignment
future-shifted leader events
same-issuer but non-leader source
```

Report detectability and economic value separately. A five-cent peak response may be valuable for RFQ skewing even when it does not justify an outright trade after costs.

## 14. Alpha 4: issuer-relative-value mean reversion

Construct an as-of public issuer-curve residual:

\[
z_{i,t}
=\frac{\widetilde P_i(t)-\widehat F_{issuer,i}(t)}
{\widehat\sigma_{i,t}}.
\]

Primary feature:

\[
x^{rv}_{i,t}=-z_{i,t}.
\]

Add only backward-looking state variables:

```text
residual age
last-trade age
liquidity bucket
issuer dispersion
market activity regime
recent own flow
recent leader flow
```

Use this as a realism alpha rather than one of the three mandatory planted-effect tests. Evaluate on `calibrated_realism` and controlled scenarios, but do not claim exact structural magnitude recovery unless a corresponding truth estimand is explicitly available.

## 15. Models

Use a staged model ladder.

### 15.1 Mandatory baselines

```text
unconditional mean/probability
single-feature OLS or logistic regression
multivariate ridge
elastic net
```

### 15.2 Nonlinear challenger

Use a restrained model available in the repository, such as scikit-learn HistGradientBoosting, only after linear baselines pass. Fix its hyperparameter grid before Gate 4. Use monotonic constraints where defensible and supported.

Do not use a highly flexible model to hide weak feature definitions.

### 15.3 Composite

Build the composite only from alphas that pass individual stability and null-control gates.

The composite must output separately:

```text
expected_clean_move_points
flow_toxicity_score
relative_value_score
confidence
forecast_horizon
valid_until
feature_contributions
model_version
```

Do not collapse return alpha and flow toxicity into one opaque score.

## 16. Evaluation

### 16.1 Predictive metrics

Report by horizon, seed, scenario, liquidity decile, and issuer size:

```text
coefficient and clustered standard error
Pearson and rank IC
out-of-sample R-squared
MAE and RMSE
sign hit rate
calibration slope and intercept
decile monotonicity
next-side log loss, Brier score, and AUC
```

### 16.2 Truth-recovery metrics

After unblinding, report:

```text
configured structural parameter
oracle state recovery
public-data recovered coefficient
relative bias
RMSE
confidence-interval coverage
sign success rate
controlled-minus-null paired difference
null fraction of controlled magnitude
```

Keep structural truth, oracle recovery, and public estimator recovery visually and numerically distinct.

### 16.3 Economic metrics

Use configurable costs. Include the current working assumption of 7.5 cents round trip when price units are par points, but treat it as a scenario rather than immutable truth.

Report:

```text
gross edge in cents
net edge after cost
turnover
event eligibility rate
capacity proxy
holding period
maximum adverse excursion
profit by liquidity decile
quote-skew value proxy
inventory-risk reduction proxy
```

Do not reject a useful RFQ feature merely because it fails a standalone round-trip trading hurdle.

## 17. Alpha controls and falsification

Implement at least:

```text
future feature shift
within-bond-day sign shuffle
notional shuffle within liquidity/side strata
issuer permutation
reverse leader/follower direction
matched cross-issuer leader
random pseudo-large-print threshold
controlled-null scenario
single-effect ablations
```

A model that performs similarly after a leakage or permutation control fails.

## 18. Alpha reproducibility and freeze

Create an immutable alpha research run:

```text
runs/alpha/<alpha_run_id>/
    resolved_alpha_config.yaml
    data_manifest.json
    feature_manifest.json
    label_manifest.json
    split_manifest.json
    seed_manifest.json
    model_selection_manifest.json
    metric_definitions.json
    plot_policy.json
    predictions/
    metrics/
    plot_data/
    figures/
    reports/
    checksums.sha256
```

The run ID must derive from content hashes, not wall-clock time.

Implement:

```bash
python -m bondalpha develop \
    --config configs/alphas/base.yaml \
    --data-root <gate3-public-root>

python -m bondalpha report \
    --run runs/alpha/<alpha_run_id>

python -m bondalpha reproduce \
    --run runs/alpha/<alpha_run_id> \
    --output runs/alpha_reproduction/<alpha_run_id>

python -m bondalpha freeze-spec \
    --run runs/alpha/<alpha_run_id>
```

The freeze must create:

```text
models/alpha_frozen/<alpha_spec_id>/
    feature_spec.yaml
    label_spec.yaml
    split_spec.yaml
    threshold_spec.yaml
    model_grid.yaml
    metric_spec.yaml
    plot_policy.yaml
    selected_model_policy.yaml
    checksums.sha256
    FROZEN
```

Gate 4 alpha evaluation must refuse to start without a frozen alpha specification.

## 19. Blinded Gate 4 alpha evaluation

Apply the frozen alpha specification to the quarantined Gate 4 public data:

```bash
python -m bondalpha evaluate-blind \
    --alpha-spec models/alpha_frozen/<alpha_spec_id> \
    --public-root data/synthetic/gate4/<gate4_run_id> \
    --output runs/alpha_gate4/<run_id>
```

This stage may calculate public-data predictive and economic metrics but must not read truth.

Freeze and hash:

```text
feature tables
labels
predictions
coefficients
public metrics
public plots
```

Only then unblind:

```bash
python -m bondalpha unblind \
    --run runs/alpha_gate4/<run_id> \
    --truth-root data/synthetic_truth/gate4/<gate4_run_id>
```

The unblind command must only add truth-comparison metrics and plots. It must not refit features or models.

## 20. Required alpha plots

Save Parquet backing data for every plot.

Produce:

```text
feature distributions by real/synthetic scenario
feature correlation and stability matrices
label availability and staleness
alpha decile response curves
coefficient by horizon and seed
rank-IC by date
calibration slope plots
controlled versus null response curves
configured versus recovered magnitude
reverse and cross-issuer controls
forest plot across seeds
cumulative gross and net edge
edge versus turnover
edge versus liquidity
flow-probability calibration
feature-contribution stability
composite contribution decomposition
```

Failed or wrong-sign results must appear in the report rather than being suppressed.

## 21. Acceptance gates

### 21.1 Gate 4 simulator

Pass only when all frozen fatal gates pass and full outputs exist with verified checksums.

### 21.2 Individual alpha recovery

For each mandatory planted alpha:

```text
correct public-data sign on at least 4 of 5 Gate 3 seeds
correct sign on the canonical Gate 4 run
median Gate 3 relative error <= 25%, or valid interval contains truth
Gate 4 truth lies within the predeclared recovery interval or failure is reported
controlled-minus-null difference has the expected sign
null magnitude <= 20% of controlled magnitude
reverse/cross-issuer controls remain near zero
no leakage/falsification control retains the original performance
```

The two additional full controlled/null seeds are robustness checks, not a new tuning set.

### 21.3 Composite alpha

Approve only if it improves frozen out-of-sample predictive or RFQ-value metrics relative to the best individual alpha without materially worsening null controls, turnover, calibration, or stability.

### 21.4 Real-data transfer

After synthetic approval, run the frozen features on a held-out real-data period. Refit only coefficients according to a separately declared real-data protocol; do not alter feature definitions after seeing the real holdout.

Synthetic success proves pipeline sensitivity and estimator recovery under known truth. It does not prove that the same economic effect exists in real markets.

## 22. Final reports

Produce:

```text
reports/gate4/<gate4_run_id>/summary.md
reports/alpha/<alpha_run_id>/development_report.md
reports/alpha_gate4/<run_id>/blinded_report.md
reports/alpha_gate4/<run_id>/truth_recovery_report.md
reports/alpha_gate4/<run_id>/rfq_translation_report.md
reports/alpha_gate4/<run_id>/decision.json
```

The final decision JSON must state separately:

```text
simulator_gate4_passed
large_print_reversal_recovered
flow_persistence_recovered
leader_follower_recovered
relative_value_predictive
composite_approved
standalone_tradeable_after_cost
useful_for_rfq_skew
approved_for_real_holdout
fatal_failures
warnings
```

## 23. Execution order

Execute in this order:

1. verify Gate 3 approval and frozen checksums;
2. implement Gate 4 resumability, streaming, and full-scale test infrastructure;
3. begin the canonical Gate 4 generation but keep its outputs quarantined from alpha development;
4. implement Alpha Factory against Gate 3 public data;
5. predeclare and freeze the alpha specification;
6. finish and structurally validate Gate 4 outputs;
7. release Gate 4 public data to the frozen alpha evaluator;
8. produce and hash the blinded Gate 4 predictions and public reports;
9. unblind once and generate truth-recovery reports;
10. run the additional full controlled/null seeds as locked robustness checks;
11. approve or reject each alpha and the composite;
12. prepare the frozen-feature real-data holdout protocol.

## 24. Final response

At completion report:

1. Gate 3 decision and frozen calibration ID;
2. Gate 4 run ID, scenarios, seeds, event counts, and storage footprint;
3. liquidity quantiles and Hawkes stability;
4. resume/reproducibility test outcomes;
5. alpha specification ID and exact feature/label horizons;
6. blinded public-data results;
7. unblinded truth-recovery results;
8. controlled-null and falsification results;
9. gross versus net economics under the configured cost scenarios;
10. which outputs are directional price alpha, flow toxicity, or relative-value signals;
11. which alphas are approved for RFQ quote skew, inventory management, outright trading, or rejected;
12. all commands run, tests passed, tests failed, and work not executed;
13. paths to public data, truth data, frozen models, predictions, reports, and decision artifacts.

Do not claim that an alpha is economically tradeable merely because it recovers a planted effect. Do not change the frozen alpha specification after Gate 4 results are visible.
