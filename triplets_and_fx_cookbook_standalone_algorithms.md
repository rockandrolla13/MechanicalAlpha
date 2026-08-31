# Triplets and FX Cookbook: Standalone Algorithm Specifications

**Purpose:** implementation-ready mathematical and algorithmic specifications for:

1. triplet momentum/reversal discovery under calendar, event, or information clocks; and
2. the seven strategies in *FX Cookbook: A Recipe for Systematic Investing in Currency Markets*.

This document deliberately excludes the wider Alpha Research Investigator architecture. It defines standalone functions, their inputs and outputs, the mathematics they implement, and the source ambiguities that must be resolved before a literal backtest is labelled complete.

---

## 0. Status and implementation rules

### 0.1 Status labels

| Label | Meaning |
| --- | --- |
| `SOURCE_LITERAL` | Directly stated by the source. |
| `SOURCE_RECONSTRUCTED` | Mechanical formalization needed to make source prose executable. |
| `PI_DECISION_REQUIRED` | The source is contradictory, incomplete, or admits multiple material choices. |
| `PROPOSED_CONTROL` | Added for scientific validity; not claimed by the source. |

### 0.2 Non-negotiable implementation rules

- Every feature uses only observations with `available_at <= decision_time`.
- Signal generation and portfolio construction are separate functions.
- Functions return diagnostics and eligibility masks as well as values.
- Missing or invalid denominators never silently become zero signals.
- A source ambiguity is a required parameter or a hard error, never an implicit default.
- Training-only objects - correlations, volatilities, betas, thresholds, selected triplets, covariance matrices - are fitted inside the training sample and frozen for validation/test scoring.
- Quote orientation is normalized before calculating signals. Define a positive return to mean appreciation of the named tradable asset in every function.

### 0.3 Canonical array convention

Unless stated otherwise:

- `T`: number of decision timestamps;
- `N`: number of instruments;
- arrays have shape `[T, N]`;
- `price[t, i]`: point-in-time tradable or fair-value price;
- `ret[t, i]`: return in the canonical positive-appreciation convention;
- `signal[t, i]`: positive means expected positive future return;
- `weight[t, i]`: positive means long the canonical asset;
- `eligible[t, i]`: point-in-time Boolean mask;
- all rolling windows are left-closed and exclude observations unavailable at `t`.

Every public function should return:

```text
Result(
    values,
    eligible,
    diagnostics,
    specification_hash,
)
```

---

# Part I - Triplet momentum/reversal methods

## 1. Mathematical object

Let a valid clock generate stopping times

$$
\tau_0 < \tau_1 < \cdots < \tau_n < \cdots,
$$

and define the sampled price

$$
P_{i,n}=P_i(\tau_n).
$$

For lag $\ell$, anchor or vantage state $a$, and future horizon $h$, define the triplet

$$
\theta=(\ell,a,h),
$$

with consecutive, non-overlapping moves

$$
L^{(\ell)}_{i,n}=P_{i,n}-P_{i,n-\ell},
\qquad
H^{(h)}_{i,n}=P_{i,n+h}-P_{i,n}.
$$

For instrument bucket $B$ and anchor state $a_n=a$,

$$
\rho_{B,\ell,a,h}
=\operatorname{SpearmanCorr}
\left(
L^{(\ell)}_{i,n},
H^{(h)}_{i,n}
\mid i\in B,\ a_n=a
\right).
$$

- $\rho>0$: continuation or momentum.
- $\rho<0$: reversal.
- $\rho=0$: null of no monotone predictive dependence.

For spread fair values $S_{i,n}$, transform spread changes into approximate price returns before applying the operator:

$$
L^{S,(\ell)}_{i,n}
=-D^S_{i,n}\left(S_{i,n}-S_{i,n-\ell}\right),
$$

$$
H^{S,(h)}_{i,n}
=-D^S_{i,n}\left(S_{i,n+h}-S_{i,n}\right).
$$

`SOURCE_RECONSTRUCTED`: use start-of-period spread duration or another frozen convention; do not use future duration.

## 2. Clock algorithms

### 2.1 `build_calendar_clock`

```text
build_calendar_clock(
    start,
    end,
    frequency,
    session_calendar,
    timezone,
    missing_interval_rule,
) -> ClockIndex
```

Algorithm:

1. Generate scheduled timestamps using the declared market calendar and timezone.
2. Remove closed intervals and holidays according to `session_calendar`.
3. Apply the frozen missing-interval rule: `no_bar`, `carry_forward`, or `interpolate`.
4. Return timestamps, session identifiers, within-session bucket, and elapsed physical time.

### 2.2 `build_event_clock`

Let $A(t)$ be cumulative eligible event count or cumulative eligible activity. For threshold $\kappa>0$,

$$
\tau_0=t_0,
\qquad
\tau_n=inf\left\{t>\tau_{n-1}:
A(t)-A(\tau_{n-1})\ge\kappa
\right\}.
$$

```text
build_event_clock(
    events,
    eligibility_rule,
    activity_measure,
    threshold_kappa,
    timestamp_field,
    tie_break_rule,
    overshoot_rule,
    session_reset,
) -> ClockIndex
```

Algorithm:

1. Sort events by the point-in-time timestamp and the frozen tie-break key.
2. Apply `eligibility_rule` using only fields known at the event timestamp.
3. Accumulate `activity_measure` after the previous clock boundary.
4. Close a bar at the first event for which cumulative activity reaches $\kappa$.
5. Apply the declared overshoot rule; do not choose it after seeing results.
6. Record physical duration, event count, notional, and clock-boundary event.

Required invariant: changing the future event stream cannot change any previously emitted $\tau_n$.

### 2.3 `build_information_clock`

Define an adapted, non-negative information increment $g(X_e;\phi)$ for event $e$, where $X_e$ is available at the event timestamp and $\phi$ is fitted using training data only:

$$
A(t)=\sum_{e:t_e\le t}g(X_e;\phi).
$$

Use the same stopping-time rule as the event clock.

```text
build_information_clock(
    events,
    fitted_information_model_phi,
    score_function_g,
    threshold_kappa,
    clock_rules,
) -> ClockIndex
```

Hard checks:

- all score inputs are contemporaneously available;
- $g\ge0$ so the activity process is non-decreasing;
- $\phi$ is fit only on the training period;
- endogenous sampling and stopping-time bias are addressed in inference;
- physical time is retained for costs, fills, latency, financing, and capacity.

## 3. Observation and target algorithms

### 3.1 `sample_state_on_clock`

```text
sample_state_on_clock(
    clock_index,
    observations,
    observation_rule,
    max_staleness,
) -> SampledPanel
```

Permitted observation rules include `last_observed`, `executable_mid`, `fair_value`, and `spread_fair_value`. Return the age of every sampled observation. Values older than `max_staleness` are ineligible, not silently carried forward.

### 3.2 `build_triplet_panel`

```text
build_triplet_panel(
    sampled_panel,
    lags,
    horizons,
    anchor_function,
    bucket_function,
    target_kind,
    duration_panel=None,
) -> TripletPanel
```

Algorithm for each $(i,n,\ell,h)$:

1. Require $n-\ell\ge0$ and $n+h<T$.
2. Compute $L^{(\ell)}_{i,n}$ using only values available at $\tau_n$.
3. Compute $H^{(h)}_{i,n}$ as the research label, never as a live feature.
4. Assign point-in-time instrument bucket $B_{i,n}$.
5. Assign anchor $a_n$ using only state known at $\tau_n$.
6. Record clock duration and mapped physical duration for both moves.
7. Mark overlapping labels so split and inference functions can purge them.

## 4. Estimation and selection algorithms

### 4.1 `estimate_triplet_family`

```text
estimate_triplet_family(
    training_triplet_panel,
    theta_registry,
    minimum_sample_size,
    inference_method,
    block_definition,
) -> TripletEstimates
```

For every pre-registered $\theta=(B,\ell,a,h)$:

1. Select eligible training observations.
2. Estimate Spearman $\widehat\rho_\theta$.
3. Estimate uncertainty using the declared dependence-aware block bootstrap, cluster bootstrap, or valid permutation design.
4. Return $\widehat\rho_\theta$, raw $p$-value, confidence interval, sample size, effective sample size, and physical-horizon distribution.
5. Do not drop failed or insignificant candidates from the multiplicity ledger.

Null and alternative:

$$
H_{0,\theta}:\rho_\theta=0,
\qquad
H_{1,\theta}:\rho_\theta\ne0,
$$

unless a one-sided sign was registered before results.

### 4.2 `adjust_triplet_multiplicity`

```text
adjust_triplet_multiplicity(
    triplet_estimates,
    method,
    family_registry,
    q_or_alpha,
) -> AdjustedTripletEstimates
```

The family includes every clock, threshold, asset bucket, anchor, lag, horizon, target, sign, and variant searched. Recommended implementations may expose Holm for family-wise control and Benjamini-Hochberg or Benjamini-Yekutieli for false-discovery control, but the method must be frozen before confirmatory evaluation.

### 4.3 `select_triplets`

```text
select_triplets(
    adjusted_training_estimates,
    selection_rule,
    top_k=None,
    minimum_effect=None,
    stability_requirements=None,
) -> FrozenTripletSet
```

Valid selection rules must be explicit. Example:

```text
eligible_theta = (
    p_adjusted <= q
    and abs(rho_hat) >= rho_min
    and effective_n >= n_eff_min
    and sign_stable_across_training_subperiods
)
selected = top_k eligible_theta ordered by abs(rho_hat)
```

Selection occurs inside training data. Validation/test data cannot determine $K$, sign, lag, horizon, anchor, clock, or threshold.

## 5. Live scoring algorithms

### 5.1 `score_triplet`

Fit the empirical training CDF $\widehat F^L_\theta$ of past moves. Define a rank-normal score

$$
z^L_{i,n,\theta}
=\Phi^{-1}\left(
\operatorname{clip}\left(
\widehat F^L_\theta(L^{(\ell)}_{i,n}),
\varepsilon,1-\varepsilon
\right)
\right).
$$

The standalone alpha is

$$
\alpha_{i,n,\theta}
=\widehat\rho_\theta z^L_{i,n,\theta}.
$$

Thus a positive past move generates a positive forecast for momentum triplets and a negative forecast for reversal triplets.

```text
score_triplet(
    current_past_move,
    frozen_triplet_estimate,
    frozen_rank_transform,
    clipping_epsilon,
) -> ScalarSignal
```

### 5.2 `aggregate_triplet_signals`

```text
aggregate_triplet_signals(
    component_signals,
    frozen_weights,
    missing_component_rule,
) -> AggregateSignal
```

Supported frozen weighting rules:

1. Equal weight:
   $$w_\theta=1/K.$$
2. Effect-to-error weight:
   $$
   \widetilde w_\theta=
   \frac{|\widehat\rho_\theta|}{\widehat{\operatorname{se}}(\widehat\rho_\theta)},
   \qquad
   w_\theta=\frac{\widetilde w_\theta}{\sum_{\theta'}\widetilde w_{\theta'}}.
   $$

Final signal:

$$
\alpha_{i,n}=\sum_{\theta\in\Theta^*}w_\theta\alpha_{i,n,\theta}.
$$

Do not re-normalize over whichever components happen to be profitable in the test period.

## 6. Clock-transfer evaluation algorithm

### `evaluate_clock_transfer`

```text
evaluate_clock_transfer(
    event_or_information_clock_result,
    matched_calendar_result,
    placebo_clock_results,
    frozen_endpoint,
    physical_time_cost_model,
    dependence_aware_inference,
) -> ClockTransferResult
```

Required comparisons:

- identical instruments and calendar sample;
- equalized decision count and gross exposure;
- matched average physical holding horizon where feasible;
- identical training/validation/test boundaries with purging in both clock and physical time;
- executable costs measured in physical time;
- pre-registered threshold robustness across $\kappa$;
- randomized-event, shifted-anchor, or channel-breaking placebo clocks.

Primary transfer estimand:

$$
\Delta_{\text{clock}}
=\mathbb E\left[R^{\mathrm{net}}_{\text{new clock}}
-R^{\mathrm{net}}_{\text{matched calendar}}\right].
$$

The new clock is not supported merely because it finds more significant triplets. It must improve the frozen out-of-sample endpoint or net economics relative to the matched control.

## 7. Triplet unit and property tests

| Test | Required result |
| --- | --- |
| Constant price | all moves zero; correlation undefined and candidate ineligible |
| Strict trend fixture | positive $\rho$ and positive continuation score |
| Alternating fixture | negative $\rho$ and reversal score |
| Future-data mutation | historical clock boundaries and live scores unchanged |
| Spread sign | tightening spread produces positive spread-implied return |
| Permuted future labels | no systematic discoveries beyond declared error rate |
| Overlap audit | split boundaries purge all shared future labels |
| Clock causality | future events cannot alter earlier event/information bars |
| Matched-control audit | decision count, exposure, sample, and cost basis reconcile |

---

# Part II - FX Cookbook strategies

## 8. Common standalone portfolio primitives

The seven signals should call common portfolio functions rather than each reimplementing normalization, neutrality, caps, and tranching.

### 8.1 `inverse_volatility_sign_weights`

Given signal $s_i$ and asset return volatility $\sigma_i>0$,

$$
u_i=\operatorname{sign}(s_i)\frac{1}{\sigma_i},
\qquad
w_i=\frac{u_i}{\sum_j|u_j|}.
$$

```text
inverse_volatility_sign_weights(signal, return_vol, eligible) -> weights
```

### 8.2 `signal_proportional_weights`

$$
w_i=\frac{s_i}{\sum_j|s_j|}.
$$

```text
signal_proportional_weights(signal, eligible) -> weights
```

### 8.3 `equal_weight_rank_halves`

1. Rank eligible assets by signal.
2. Long the top half and short the bottom half.
3. Assign equal absolute weights within each half.
4. Normalize $\sum_i|w_i|=1$.

```text
equal_weight_rank_halves(signal, eligible, tie_rule) -> weights
```

### 8.4 `linear_rank_halves`

For $m$ assets in each half, give within-half rank $r=1$ to the weakest and $r=m$ to the strongest. Long-side weights are

$$
w_r^{+}=\frac{1}{2}\frac{r}{\sum_{k=1}^{m}k},
$$

and short-side weights have the opposite sign.

```text
linear_rank_halves(signal, eligible, tie_rule) -> weights
```

### 8.5 `project_beta_neutral`

Given preliminary weights $\widetilde w$ and frozen USD-factor betas $\beta^\$$, solve

$$
\min_w\sum_i(w_i-\widetilde w_i)^2
$$

subject to

$$
\sum_iw_i\beta_i^\$=0,
\qquad
\sum_i|w_i|=1,
\qquad
\underline w_i\le w_i\le\overline w_i.
$$

```text
project_beta_neutral(preliminary_weights, usd_betas, bounds) -> weights
```

The cookbook uses the first principal component of the USD/FX basket as the USD factor. Betas must be estimated point-in-time.

### 8.6 `apply_position_bounds`

The source upper bound is the smaller of:

- 15% absolute portfolio weight; and
- 2% of the currency's average daily volume for a USD 1bn portfolio.

The lower bound is symmetric. The cap application and re-normalization algorithm must be iterative so clipping one asset does not violate gross exposure or neutrality elsewhere.

```text
apply_position_bounds(weights, adv, portfolio_notional, hard_cap=0.15, adv_fraction=0.02) -> weights
```

### 8.7 `tranche_rebalance`

For $K$ tranches with independent vintage targets $w^{*(k)}_t$,

$$
w_t=\frac1K\sum_{k=1}^{K}w^{*(k)}_t.
$$

```text
tranche_rebalance(target_weight_stream, rebalance_frequency, tranche_frequency, K) -> held_weights
```

Every strategy must separately define target-weight refresh, execution delay, holidays, forward rolls, transaction costs, and unavailable-instrument treatment.

---

## 9. Strategy 1 - Price Momentum

### 9.1 Standalone functions

```text
compute_total_return_momentum_signal(...)
apply_momentum_hysteresis(...)
scale_by_signal_dispersion(...)
residualize_fx_returns(...)
build_momentum_time_series_weights(...)
build_momentum_cross_sectional_weights(...)
```

### 9.2 Inputs

- daily total returns, including spot and carry;
- point-in-time return volatility;
- for cross-sectional implementation: USD/FX first principal component and rolling factor betas;
- previous accepted signal for hysteresis;
- eligibility, ADV, and position bounds.

### 9.3 Raw signal

For lookback $q$,

$$
R_{i,t-q:t}=\prod_{u=t-q+1}^{t}(1+r_{i,u})-1,
\qquad
\widetilde s_{i,t,q}=\operatorname{sign}(R_{i,t-q:t}).
$$

For a declared lookback set $\mathcal Q$,

$$
\overline s_{i,t}=\frac{1}{|\mathcal Q|}
\sum_{q\in\mathcal Q}\widetilde s_{i,t,q},
$$

$$
\widehat\sigma^{s}_{i,t}
=\sqrt{
\frac{1}{d_{\mathcal Q}}
\sum_{q\in\mathcal Q}
(\widetilde s_{i,t,q}-\overline s_{i,t})^2
}.
$$

`PI_DECISION_REQUIRED - MOM-001`: the prose states 232 lookbacks, $\mathcal Q=\{21,\ldots,252\}$; the displayed equation uses $q=32,\ldots,251$ and an inconsistent denominator. The implementation must require explicit `lookback_set` and `dispersion_denominator`; it must not select either silently.

### 9.4 Hysteresis and noise scaling

The prose states an absolute threshold $\theta=1/3$:

$$
\widehat s_{i,t}=
\begin{cases}
\operatorname{sign}(\overline s_{i,t}), &
|\overline s_{i,t}|\ge\theta,\\
\widehat s_{i,t-1}, &
|\overline s_{i,t}|<\theta.
\end{cases}
$$

The final signal is

$$
s^{\mathrm{mom}}_{i,t}
=\frac{\widehat s_{i,t}}
{\max(\widehat\sigma^s_{i,t},\sigma^s_{\mathrm{floor},t})},
$$

where the source sets the floor to the cross-asset 25th percentile of signal-dispersion estimates.

`PI_DECISION_REQUIRED - MOM-002`: the displayed branch condition omits the absolute value although the prose explicitly includes it. A literal implementation should expose `threshold_mode = prose_absolute | displayed_signed` and remain blocked until selected.

### 9.5 Time-series algorithm

1. Calculate the total-return signal.
2. Apply hysteresis and dispersion scaling.
3. Convert to preliminary weights using signal divided by asset return volatility:
   $$
   u_{i,t}=s^{\mathrm{mom}}_{i,t}/\sigma^r_{i,t}.
   $$
4. Normalize gross exposure to one.
5. Apply asset caps and ADV limits.
6. Rebalance monthly using 20 daily tranches.

### 9.6 Cross-sectional algorithm

First estimate point-in-time residual returns with a one-year rolling regression:

$$
r_{i,t}=\alpha_{i,t}+\beta_{i,t}r^\$_t+\varepsilon_{i,t},
$$

where $r^\$_t$ is the USD/FX first principal component return. Rebuild the multi-lookback signal from $\varepsilon_{i,t}$.

Then:

1. Use the continuous residual signal rather than reducing it to sign.
2. Apply hysteresis and dispersion scaling using the frozen interpretation of MOM-002.
3. Rank eligible currencies.
4. Long the top half and short the bottom half with equal weights.
5. Project weights to zero USD-factor beta.
6. Apply caps and normalize gross exposure to one.
7. Rebalance monthly using 20 daily tranches.

### 9.7 Minimum tests

- all-positive returns produce a positive time-series signal;
- reciprocal quote conversion preserves the economic position after sign normalization;
- $|\overline s|<1/3$ preserves the prior signal under the prose interpretation;
- zero dispersion invokes the floor;
- residual returns have near-zero fitted USD beta in training data;
- final cross-sectional weights satisfy gross-one and beta-zero constraints.

---

## 10. Strategy 2 - Carry

### 10.1 Standalone functions

```text
compute_fx_carry(...)
smooth_and_risk_adjust_carry(...)
build_carry_time_series_weights(...)
solve_carry_max_sharpe_weights(...)
```

### 10.2 Raw and smoothed signal

For source spot $S_{i,t}$ and forward $F_{i,t}$,

$$
c_{i,t}=\frac{S_{i,t}-F_{i,t}}{F_{i,t}}.
$$

For smoothing window $N_c$,

$$
\overline c_{i,t}=\frac1{N_c}
\sum_{q=0}^{N_c-1}c_{i,t-q},
$$

and the risk-adjusted carry signal is

$$
s^{\mathrm{carry}}_{i,t}
=\frac{\overline c_{i,t}}{\sigma^r_{i,t}}.
$$

`PI_DECISION_REQUIRED - CARRY-001`: the source does not specify $N_c$ in the signal-generation section.

`PI_DECISION_REQUIRED - CARRY-002`: $(S-F)/F$ changes economic interpretation with quote convention. `compute_fx_carry` must accept base currency, quote currency, tradable asset, and long-position definition, and verify that positive signal means positive expected return in the canonical orientation.

### 10.3 Time-series algorithm

1. Normalize quotes.
2. Calculate $c$, $\overline c$, and $s^{\mathrm{carry}}$.
3. Use signal-proportional weights:
   $$
   w_{i,t}=s^{\mathrm{carry}}_{i,t}/\sum_j|s^{\mathrm{carry}}_{j,t}|.
   $$
4. Apply caps and gross normalization.
5. Rebalance monthly with 20 daily tranches.

### 10.4 Market-neutral maximum ex-ante Sharpe algorithm

Given current carry vector $c$ or a frozen choice of smoothed carry and point-in-time covariance $\Sigma_t$, solve

$$
\max_w
\frac{w^\top c}{\sqrt{w^\top\Sigma_t w}}
$$

subject to

$$
w^\top\beta^\$=0,
\qquad
\sum_i|w_i|=1,
\qquad
\underline w_i\le w_i\le\overline w_i.
$$

`PI_DECISION_REQUIRED - CARRY-003`: freeze whether the optimizer's reward vector is raw carry $c$, smoothed carry $\overline c$, or risk-adjusted signal $s^{\mathrm{carry}}$. The source prose and displayed objective should be reconciled visually before coding the literal version.

### 10.5 Minimum tests

- covered-interest-parity fixture produces the expected carry sign;
- reciprocal quotes lead to the same economic position after normalization;
- constant carry is unchanged by smoothing;
- covariance matrix is point-in-time positive semidefinite or repaired by a frozen rule;
- optimizer satisfies beta, gross, and bound constraints;
- no position is produced until CARRY-001 to CARRY-003 are resolved.

---

## 11. Strategy 3 - Fundamental Value

### 11.1 Standalone functions

```text
fit_reer_dols_panels(...)
compute_reer_misalignment(...)
convert_reer_to_usd_fx_misalignment(...)
build_value_time_series_weights(...)
build_value_cross_sectional_weights(...)
```

### 11.2 Point-in-time inputs

- BIS broad real effective exchange rate;
- real GDP per capita for the country and trade-weighted comparison basket;
- terms-of-trade series;
- frozen panel membership;
- data vintages, revisions, and publication lags;
- USD/FX rates and volatility;
- USD-factor betas.

The source uses five panels:

1. EM commodity exporters;
2. EM commodity importers;
3. East Asian economies;
4. G10 commodity exporters;
5. G10 commodity importers.

### 11.3 DOLS fair-value model

Define productivity differential

$$
\operatorname{PROD}_{i,t}
=\log\left(
\frac{\operatorname{GDPpc}_{i,t}}
{\overline{\operatorname{GDPpc}}_{B(i),t}}
\right),
$$

and terms of trade

$$
\operatorname{TOT}_{i,t}
=\log(\operatorname{TOTIndex}_{i,t}).
$$

For panel $p$, estimate

$$
\log(\operatorname{REER}_{i,t})
=\alpha_i
+\beta_{p,1}\operatorname{PROD}_{i,t}
+\beta_{p,2}\operatorname{TOT}_{i,t}
+\sum_{s=-1}^{1}
\left[
\gamma_{p,s,1}\Delta\operatorname{PROD}_{i,t-s}
+\gamma_{p,s,2}\Delta\operatorname{TOT}_{i,t-s}
\right]
+\varepsilon_{i,t}.
$$

The source's compact display is OCR-sensitive. The final literal equation must be verified against the page image before implementation.

The trade-weighted REER misalignment is $\varepsilon_{i,t}$.

### 11.4 USD/FX conversion

Convert the vector of trade-weighted REER misalignments into bilateral USD/FX misalignments:

$$
s^{\mathrm{value}}_t
=\mathcal M(\varepsilon_t,W_t),
$$

where $W_t$ is the trade-weight matrix.

`PI_DECISION_REQUIRED - VALUE-001`: the source names two methods - matrix inversion and least squares - without selecting one unique implementation. `convert_reer_to_usd_fx_misalignment` must require `method = matrix_inversion | least_squares` plus the precise normalization constraint.

### 11.5 Time-series algorithm

1. Fit expanding or frozen-vintage panel DOLS using only available releases.
2. Calculate current residual misalignment.
3. Convert REER misalignment to USD/FX misalignment using the selected method.
4. Orient the sign so positive means undervalued and expected appreciation.
5. Risk-adjust:
   $$
   z^{\mathrm{value}}_{i,t}=s^{\mathrm{value}}_{i,t}/\sigma^r_{i,t}.
   $$
6. Use signal-proportional weights and apply bounds.
7. Rebalance annually, tranched monthly.

### 11.6 Cross-sectional algorithm

1. Rank risk-adjusted misalignments.
2. Long the undervalued half and short the overvalued half.
3. Use `linear_rank_halves`, not equal weights.
4. Project to zero USD-factor beta.
5. Apply bounds and normalize gross exposure.
6. Rebalance monthly.

### 11.7 Minimum tests

- revised macro observations are unavailable before their historical release timestamps;
- a currency exactly at fitted fair value has zero misalignment;
- conversion method satisfies its declared cross-rate or normalization identities;
- the most undervalued currency receives the largest long weight;
- final cross-sectional portfolio is beta-neutral and gross-one;
- changing VALUE-001 is recorded as a separate strategy variant.

---

## 12. Strategy 4 - Rates Momentum Spill-Over

### 12.1 Standalone functions

```text
compute_six_month_rate_differential(...)
compute_rates_momentum_spillover_signal(...)
fit_rates_fx_sign_filter(...)
build_mso_time_series_weights(...)
build_mso_cross_sectional_weights(...)
```

### 12.2 Signal

Let $d^{6m}_{i,t}$ be the country-minus-US six-month interest-rate differential implied consistently from six-month FX forwards. For windows

$$
\mathcal W=\{21,42,63\}\text{ business days},
$$

calculate annualized changes

$$
\Delta^{(q)}d^{6m}_{i,t}
=A_q\left(d^{6m}_{i,t}-d^{6m}_{i,t-q}\right),
$$

and annualized volatility of daily changes over the same window

$$
\sigma^{d,(q)}_{i,t}
=\operatorname{AnnualizedSD}
\left(\Delta d^{6m}_{i,u}:u=t-q+1,\ldots,t\right).
$$

Combine the three standardized changes:

$$
x^{\mathrm{MSO}}_{i,t}
=\frac13\sum_{q\in\mathcal W}
\frac{\Delta^{(q)}d^{6m}_{i,t}}
{\sigma^{d,(q)}_{i,t}}.
$$

Apply one-month smoothing:

$$
s^{\mathrm{MSO}}_{i,t}
=\frac1{N_{1m}}
\sum_{u=0}^{N_{1m}-1}x^{\mathrm{MSO}}_{i,t-u}.
$$

`SOURCE_RECONSTRUCTED`: make the annualization convention and the number of business days representing one month explicit.

### 12.3 Sign filter

Using a trailing one-year training window, estimate the correlation between a past one-day change in the rate differential and the subsequent one-day FX return:

$$
\chi_{i,t}
=\operatorname{Corr}
\left(
\Delta d^{6m}_{i,u},
r^{FX}_{i,u+1}
\right)_{u\in\mathcal T_t^{1y}}.
$$

Eligibility is

$$
e^{\mathrm{MSO}}_{i,t}=\mathbf1\{\chi_{i,t}\ge0\}.
$$

The filter must be fitted without using the current or future label. Freeze how a zero correlation and insufficient history are handled.

### 12.4 Time-series algorithm

1. Calculate and smooth the MSO signal.
2. Apply the sign filter.
3. Use `inverse_volatility_sign_weights` based on asset return volatility.
4. Apply bounds and gross normalization.
5. Rebalance weekly.

### 12.5 Cross-sectional algorithm

1. Filter the universe before ranking.
2. Rank eligible signals.
3. Use equal-weight top and bottom halves.
4. Project to zero USD-factor beta.
5. Apply bounds and gross normalization.
6. Rebalance weekly.

### 12.6 Minimum tests

- a steadily rising rate differential creates positive raw MSO before orientation adjustments;
- zero rate-change volatility makes the instrument ineligible;
- a negative fitted rate-to-FX relationship removes the asset before ranking;
- filter estimation does not use future returns beyond its fit cutoff;
- weekly portfolio obeys bounds, gross-one, and cross-sectional beta neutrality.

---

## 13. Strategy 5 - COFFEE/DTCC Positioning

### 13.1 Standalone functions

```text
normalize_option_direction(...)
filter_coffee_options(...)
compute_coffee_imbalance(...)
build_coffee_time_series_weights(...)
build_coffee_cross_sectional_weights(...)
```

### 13.2 Option eligibility

For each European FX option observation:

$$
e_{o,t}
=\mathbf1\left\{
0.25\le|\Delta_{o,t}|\le0.75,
\quad 0<\operatorname{TTM}_{o,t}<1\text{ year}
\right\}.
$$

The source excludes options expiring on the signal-evaluation date.

### 13.3 Signal

After normalizing option direction so a call represents upside in the canonical asset, aggregate eligible call and put notionals over the trailing four weeks:

$$
I^{4w}_{i,t}
=\sum_{u\in(t-4w,t]}
\left(
V^{\mathrm{call}}_{i,u}
-V^{\mathrm{put}}_{i,u}
\right).
$$

Let $\sigma^{I,1y}_{i,t}$ be the trailing one-year historical volatility of the daily imbalance measure. Then

$$
s^{\mathrm{COFFEE}}_{i,t}
=\frac{I^{4w}_{i,t}}{\sigma^{I,1y}_{i,t}}.
$$

`PI_DECISION_REQUIRED - COFFEE-001`: define notional currency and normalize call/put direction across reciprocal FX quotes. A USD call is not economically comparable to a foreign-currency call without this mapping.

`PI_DECISION_REQUIRED - COFFEE-002`: define whether one-year volatility is calculated from daily four-week rolling imbalances or from unsmoothed daily call-minus-put flow. The prose should be reconciled with the original implementation or source exhibit.

### 13.4 Time-series algorithm

1. Normalize option and notional direction.
2. Filter by delta and expiry.
3. Aggregate four-week call-minus-put notional.
4. Standardize by the frozen one-year imbalance-volatility definition.
5. Use `inverse_volatility_sign_weights` based on underlying return volatility.
6. Apply bounds and gross normalization.
7. Rebalance weekly with daily tranching.

### 13.5 Cross-sectional algorithm

1. Rank COFFEE signals.
2. Use equal-weight top and bottom halves.
3. Project to zero USD-factor beta.
4. Apply bounds and gross normalization.
5. Rebalance weekly with daily tranching.

### 13.6 Minimum tests

- all-call fixture gives a positive normalized imbalance;
- reciprocal quote representation preserves the economic signal;
- options outside delta or expiry bounds contribute zero;
- no signal is emitted when historical imbalance volatility is zero;
- weekly/daily tranche accounting reconciles to held portfolio weights.

---

## 14. Strategy 6 - CFTC Continuation

### 14.1 Standalone functions

```text
align_cot_release_to_trade_date(...)
compute_cftc_continuation_signal(...)
build_cftc_continuation_time_series_weights(...)
build_cftc_continuation_cross_sectional_weights(...)
```

### 14.2 Availability rule

The weekly COT report is released Friday at 15:30 ET using positions from the prior Tuesday close. The cookbook's conservative backtest trades the following Monday, described as a four-business-day delay from the position snapshot.

```text
available_at = official_release_timestamp
first_trade_time = next_declared_Monday_execution_time_after_release
```

Holiday and late-release behavior must be deterministic.

### 14.3 Signal

Let $l^{NC}_{i,t}$ and $s^{NC}_{i,t}$ be non-commercial long and short positions for report week $t$. Aggregate four weekly observations:

$$
L^{NC}_{i,t}=\sum_{q=0}^{3}l^{NC}_{i,t-q},
\qquad
S^{NC}_{i,t}=\sum_{q=0}^{3}s^{NC}_{i,t-q}.
$$

Then

$$
s^{\mathrm{CFTC,C}}_{i,t}
=\frac{L^{NC}_{i,t}-S^{NC}_{i,t}}
{L^{NC}_{i,t}+S^{NC}_{i,t}}.
$$

If the denominator is zero or a position is missing, the asset is ineligible.

### 14.4 Time-series algorithm

1. Align the report to its first executable date.
2. Calculate the four-week continuation ratio.
3. Normalize contract direction into the canonical FX asset.
4. Use `inverse_volatility_sign_weights`.
5. Apply bounds and gross normalization.
6. Rebalance weekly.

### 14.5 Cross-sectional algorithm

1. Rank continuation signals.
2. Use equal-weight top and bottom halves.
3. Project to zero USD-factor beta.
4. Apply bounds and gross normalization.
5. Rebalance weekly.

### 14.6 Minimum tests

- net-long non-commercial positioning gives a positive continuation signal;
- signal lies in $[-1,1]$ when positions are non-negative;
- Tuesday data cannot affect a position before the following declared execution time;
- contract and quote orientation preserve the economic direction;
- final cross-sectional weights satisfy beta neutrality.

---

## 15. Strategy 7 - CFTC Reversal

### 15.1 Standalone functions

```text
compute_cftc_net_position(...)
compute_cftc_reversal_signal(...)
build_cftc_reversal_cross_sectional_weights(...)
run_cftc_discretization_sensitivity(...)
```

### 15.2 Signal

Define current net non-commercial position

$$
n^{NC}_{i,t}=l^{NC}_{i,t}-s^{NC}_{i,t}.
$$

For lookback windows $m\in\{1,2,3\}$ months,

$$
z^{(m)}_{i,t}
=\frac{n^{NC}_{i,t}-\mu^{(m)}_{i,t}}
{\sigma^{(m)}_{i,t}},
$$

and

$$
\overline z_{i,t}=\frac13
\sum_{m\in\{1,2,3\}}z^{(m)}_{i,t}.
$$

Let $\sigma^{r,6m}_{i,t}$ be the trailing six-month volatility of daily underlying FX returns. The reversal signal is

$$
s^{\mathrm{CFTC,R}}_{i,t}
=-\frac{\overline z_{i,t}}
{\sigma^{r,6m}_{i,t}}.
$$

The source applies no further smoothing in order to preserve speed.

`PI_DECISION_REQUIRED - CFTC-R-001`: COT observations are weekly while z-score windows are stated in months. Freeze the exact observation counts or calendar-window implementation for 1, 2, and 3 months.

### 15.3 Cross-sectional-only algorithm

1. Apply the same release-to-trade-date lag as CFTC continuation.
2. Calculate current net position.
3. Calculate the three point-in-time z-scores.
4. Average, divide by six-month daily return volatility, and invert the sign.
5. Rank signals.
6. Use equal-weight top and bottom halves.
7. Do **not** apply the USD-beta constraint: the source removes it because the unconstrained historical construct was already market-neutral.
8. Apply position bounds and normalize gross exposure.
9. Rebalance weekly.

The cookbook rejects the time-series reversal implementation for lack of predictive power; do not expose it as a literal strategy.

### 15.4 Discretization sensitivity

```text
run_cftc_discretization_sensitivity(
    frozen_signal_panel,
    bump_distribution,
    number_of_simulations,
    frozen_portfolio_algorithm,
) -> SensitivityDistribution
```

The source perturbs each asset/date signal by a small quantity and reruns the portfolio to assess Sharpe sensitivity. Treat this as a robustness diagnostic, not as signal estimation and not as evidence that data revisions are random.

### 15.5 Minimum tests

- an unusually large net long creates a negative reversal signal;
- constant positioning makes z-score undefined and asset ineligible;
- current-week report is unavailable until official release and execution lag;
- no time-series reversal portfolio is emitted by the literal factory;
- no USD-beta constraint is added to the cross-sectional literal implementation;
- CFTC-R-001 variants receive distinct specification hashes.

---

# Part III - Standalone function registry

## 16. Recommended module boundary

```text
triplets/
  clocks.py
    build_calendar_clock
    build_event_clock
    build_information_clock
  panel.py
    sample_state_on_clock
    build_triplet_panel
  inference.py
    estimate_triplet_family
    adjust_triplet_multiplicity
    select_triplets
  signal.py
    score_triplet
    aggregate_triplet_signals
  evaluation.py
    evaluate_clock_transfer

fx_cookbook/
  common.py
    inverse_volatility_sign_weights
    signal_proportional_weights
    equal_weight_rank_halves
    linear_rank_halves
    project_beta_neutral
    apply_position_bounds
    tranche_rebalance
  momentum.py
  carry.py
  value.py
  rates_momentum_spillover.py
  coffee.py
  cftc_continuation.py
  cftc_reversal.py
```

## 17. Factory outputs

Each signal module should expose two levels:

```text
compute_<strategy>_signal(inputs, frozen_signal_spec) -> SignalResult
build_<strategy>_weights(signal_result, risk_inputs, frozen_portfolio_spec) -> WeightResult
```

The triplet package should expose:

```text
fit_triplet_method(training_data, frozen_research_spec) -> FittedTripletMethod
score_triplet_method(live_or_test_data, fitted_method) -> SignalResult
```

This separation ensures that:

- a signal can be tested without a portfolio optimizer;
- portfolio changes do not redefine the alpha;
- time-series and cross-sectional implementations can share one signal;
- alternative clocks can share the same triplet operator while retaining distinct fitted objects and inference;
- every ambiguity resolution changes the specification hash and therefore creates a traceable variant.

## 18. Blocking decision registry

| ID | Method | Required decision |
| --- | --- | --- |
| `MOM-001` | Momentum | Use prose lookbacks 21-252 or displayed 32-251, and choose the matching denominator. |
| `MOM-002` | Momentum | Use absolute hysteresis threshold from prose or signed displayed branch. |
| `CARRY-001` | Carry | Select smoothing window $N_c$. |
| `CARRY-002` | Carry | Freeze quote orientation and positive-position convention. |
| `CARRY-003` | Carry | Freeze optimizer reward vector: raw, smoothed, or risk-adjusted carry. |
| `VALUE-001` | Value | Select REER-to-USD/FX conversion and normalization. |
| `COFFEE-001` | COFFEE | Normalize option direction and notional across reciprocal quotes. |
| `COFFEE-002` | COFFEE | Define the one-year imbalance-volatility input series. |
| `CFTC-R-001` | CFTC Reversal | Map 1/2/3-month windows to weekly observations or calendar windows. |

No literal implementation should be labelled `IMPLEMENTATION_READY` while its listed decision remains unresolved.

## 19. Suggested implementation sequence

1. Implement and property-test the common portfolio primitives.
2. Implement the calendar-time triplet operator on synthetic fixtures.
3. Add event and information clocks without changing the triplet estimator API.
4. Implement CFTC continuation, the simplest fully specified cookbook signal after direction and release alignment are fixed.
5. Implement Rates Momentum Spill-Over and COFFEE.
6. Implement CFTC reversal with explicit discretization variants.
7. Implement Momentum, Carry, and Value only after their blocking decisions are recorded.

This ordering is an engineering dependency order, not a claim about expected profitability.

