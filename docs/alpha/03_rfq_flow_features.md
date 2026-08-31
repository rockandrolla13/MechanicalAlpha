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
- execution-to-inquiry ratio
- firm-up-to-inquiry ratio
- TRACE-to-RFQ activity ratio

The baseline is as-of and same-hour only.
If the prior same-hour baseline has fewer than three observations, the feature is missing.

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
- It does not fit models.
- It does not calculate labels.
- TRACE side must be validated before TRACE signed features are treated as observed customer-side features.
