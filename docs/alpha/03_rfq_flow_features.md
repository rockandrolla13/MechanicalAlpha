# RFQ Flow Feature Contract

This stage defines deterministic microstructure feature formulas only.
It does not fit predictive models.

All features consume the canonical `AlphaInputBundle`.
The feature code does not query `marketdb`.
Source adapters must normalize side before feature calculation.

## Side Convention

The feature library uses the customer-side convention:

```text
customer buy  = +1
customer sell = -1
```

If a source has dealer-perspective side or source-defined side, the adapter must document the transformation before the feature code sees it.
TRACE side is usable only when the source side has been documented or separately validated.

## Point-In-Time Rule

For a prediction timestamp `t`, every feature window uses only observations with:

```text
observation_timestamp < t
```

Rows at exactly `t` are excluded.
This avoids using the event being predicted as its own feature.

## Implemented Families

### A1 RFQ Count Imbalance

Formula:

```text
(w_buy * buy_measure_w - w_sell * sell_measure_w)
/ (w_buy * buy_measure_w + w_sell * sell_measure_w + epsilon)
```

The legacy unweighted count output is still available for comparison.
The fitted path estimates `w_buy` and `w_sell` from training-period market totals only.
The default fitted weighting is inverse market share, so persistent market buy/sell drift is neutral in expectation.

Supported measures:

- `count`
- `cr01`, when event-level CR01 is present

Implemented for:

- all RFQ inquiries
- firm inquiries
- firm-ups
- RFQ executions
- TRACE trades where side is valid

Supported clocks:

- configurable calendar windows
- configurable event windows

### A2 RFQ Notional Imbalance

Formula:

```text
sum(w_side_j * customer_side_j * transformed_risk_j)
/ (sum(w_side_j * abs(transformed_risk_j)) + epsilon)
```

The fitted path prefers CR01 as the traded-risk measure.
Notional remains available as an explicitly separate measure.
The alpha does not replace missing CR01 with notional inside a CR01 feature.

The fitted buy/sell weights are learned from training-period market totals.
This prevents a persistent buy or sell drift from being treated as a balanced market.

Variants:

- raw risk
- `log1p` risk
- capped risk
- square-root risk

### A3 Buy/Sell Intensity Pressure

Formula:

```text
lambda_buy_count  = sum(exp(-log(2) * age_seconds_j / half_life_seconds)) / half_life_seconds
lambda_sell_count = same calculation for customer sells

lambda_buy_cr01  = sum(CR01_j * exp(-log(2) * age_seconds_j / half_life_seconds)) / half_life_seconds
lambda_sell_cr01 = same calculation for customer sells
```

The default half-lives are now days-scale for corporate bonds.
The fitted path searches configured candidates, currently:

```text
1d, 2d, 5d, 10d, 20d, 40d
```

Selection uses training-period rows only.
For each candidate half-life, the alpha compares EWMA-implied expected counts with observed future training-window counts using Poisson deviance.
For CR01 clocks, the same train-only candidate search compares EWMA-implied expected CR01 risk flow with observed future CR01 risk flow.
The selected half-life and side-specific empirical baseline are frozen before scoring validation, test, or live-style rows.

RFQ CR01 is the primary fitted clock when available.
TRACE/event count clocks remain available as separate outputs.
The code does not map static bond DV01 or CR01 into traded risk.
CR01 must be present on the event or RFQ row to produce CR01 intensity features.

Derived features:

- buy intensity
- sell intensity
- intensity difference
- intensity ratio
- log intensity ratio
- fitted buy expected intensity
- fitted sell expected intensity
- buy intensity surprise
- sell intensity surprise
- buy-minus-sell intensity surprise
- fitted buy expected CR01 intensity
- fitted sell expected CR01 intensity
- buy CR01 intensity surprise
- sell CR01 intensity surprise
- buy-minus-sell CR01 intensity surprise

The EWMA decay uses elapsed clock time.
It does not assume regular observations.

### A4 Last-Side Persistence And Switching State

Features:

- last RFQ side
- last TRACE side
- same-side run length
- elapsed time since side change
- fraction of last `N` events with the same side as the latest prior event
- last-side multiplied by count imbalance
- last-side multiplied by notional imbalance
- empirical switching hazard

### A5 Multi-Clock Activity Surprise

Features:

- RFQ event-count surprise
- RFQ notional surprise
- TRACE event-count surprise
- TRACE notional surprise
- gross and signed DV01 surprise, when DV01 is present
- gross and signed CR01 surprise, when CR01 is present
- issuer-level event, notional, DV01, and CR01 surprise
- bond share of issuer activity surprise
- execution-to-inquiry ratio
- firm-up-to-inquiry ratio
- TRACE-to-RFQ activity ratio

The baseline is fitted on the training period only.
The scoring path uses the frozen fitted baseline for validation, test, and live-style replay.

Default candidate calendar windows:

```text
5h, 1d, 2d, 5d, 10d, 20d, 40d
```

Default RFQ event windows:

```text
last 5, last 10, last 25, last 50 RFQs
```

Default TRACE or execution windows:

```text
last 5, last 10, last 25, last 50 trades
```

The fitted baseline first attempts a simple Poisson GLM for count targets when the training sample is large enough.
The GLM uses training-only context columns:

```text
hour, weekday, liquidity_bucket, rating_bucket, sector, maturity_bucket
```

If the GLM is sparse, unstable, non-finite, or unavailable, the alpha uses a hierarchical empirical population baseline.
The empirical baseline falls back through:

```text
bond -> issuer -> liquidity bucket -> rating/sector/maturity bucket -> global
```

The primary standardized surprise is:

```text
(observed_activity - expected_activity) / fitted_residual_scale
```

Separate activity targets are kept for:

```text
event_count
notional
signed_notional
gross_dv01
signed_dv01
gross_cr01
signed_cr01
```

where:

```text
signed_notional = customer_side * notional
gross_dv01 = abs(dv01)
signed_dv01 = customer_side * dv01
gross_cr01 = abs(cr01)
signed_cr01 = customer_side * cr01
```

Issuer fields use the same calculations aggregated across all bonds with the same `issuer_id`.
Bond-versus-issuer fields compare the bond's observed share of issuer activity with its frozen expected share.
Ratio features compare observed ratios with frozen expected ratios fitted on the training period.

The current ratios are:

```text
execution_to_inquiry
firmup_to_inquiry
trace_to_rfq
```

If DV01 or CR01 is missing, the corresponding feature is missing with a quality flag.
The feature does not silently replace missing risk with notional.
Static bond-level DV01 or CR01 can be used only when the alpha config explicitly declares the unit policy.
For example, a `per_1mm_notional` setting scales the static risk by the event notional.
The default config disables this fallback.

### A6 Spread-Conditioned Flow Pressure

Features:

- latest composite spread
- latest spread percentile
- bid/ask asymmetry
- composite-source disagreement, when available
- composite staleness
- flow pressure multiplied by spread
- flow pressure multiplied by spread percentile
- flow pressure multiplied by composite staleness
- liquidity bucket passthrough

The quote used is the latest quote strictly before the prediction timestamp.

### A16 RFQ Scarcity And Disagreement

Features:

- latest observable responder count
- response scarcity
- latest dealer count
- quote dispersion
- response latency
- no-response rate
- firm-up rate
- execution rate
- age of latest executable indication

Unavailable RFQ fields produce missing values.
They are not inferred from unrelated fields.

## Diagnostics

The diagnostic helper reports:

- non-null rate
- zero rate
- unique-value count
- constant columns
- sparse columns
- extreme numeric values

When bond metadata are supplied, group coverage is attached for available rating, sector, duration, liquidity bucket, and issuer fields.

## Current Limitations

- The implementation is deterministic and local.
- It is intentionally not optimized for very large production panels yet.
- A5 fits an activity baseline model.
- The other A-family flow features remain deterministic formulas.
- It does not calculate labels.
- TRACE side must be validated before TRACE signed features are treated as observed customer-side features.
