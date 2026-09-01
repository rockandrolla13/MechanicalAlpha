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
(customer_buy_count_w - customer_sell_count_w)
/ (customer_buy_count_w + customer_sell_count_w + epsilon)
```

Implemented for:

- all RFQ inquiries
- firm inquiries
- firm-ups
- RFQ executions
- TRACE trades where side is valid

Supported clocks:

- calendar windows: `30m`, `2h`
- event windows: `last_5`, `last_10`, `last_25`

### A2 RFQ Notional Imbalance

Formula:

```text
sum(customer_side_j * transformed_notional_j)
/ (sum(abs(transformed_notional_j)) + epsilon)
```

Variants:

- raw notional
- `log1p` notional
- prior-window p95 capped notional
- square-root notional

### A3 Buy/Sell Intensity Pressure

Formula:

```text
lambda_buy  = sum(exp(-log(2) * age_seconds_j / half_life_seconds)) / half_life_seconds
lambda_sell = same calculation for customer sells
```

Derived features:

- buy intensity
- sell intensity
- intensity difference
- intensity ratio
- log intensity ratio

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
