# ETF Options Positioning

## Status

Implemented as `ETF_OPT_POSITIONING`.

This is a fixed-income ETF adapter for the cookbook COFFEE/DTCC positioning idea.
It is not the FX source-literal COFFEE strategy.
The FX literal strategy remains blocked by `COFFEE-001` and `COFFEE-002`.

## What It Measures

The signal measures whether recent point-in-time ETF options positioning is skewed toward calls or puts.

Positive means call notional exceeds put notional after eligibility filters.
That is interpreted as upside demand in the ETF.

## Supported Instruments

- Fixed-income ETFs: supported when options positioning data are available.
- Corporate bonds: not directly supported.
- Bond baskets: derivable only through an explicit ETF-to-bond exposure map.

## Required Inputs

The alpha reads `AlphaInputBundle.external_factors`.

Required columns:

```text
timestamp
factor_id
value
asset_id or bond_id or etf_ticker
option_type
option_delta
option_ttm_days
option_notional
```

Recommended columns:

```text
publication_timestamp
expiry_date
source
```

The default `factor_id` is:

```text
etf_option_position
```

## Point-In-Time Rule

At prediction timestamp `t`, an option row is usable only when:

```text
publication_timestamp <= t
timestamp < t
```

If `publication_timestamp` is missing, the adapter treats `timestamp` as the publication time.
That is conservative only when the source timestamp is already an availability timestamp.

Rows expiring on the prediction date are excluded when `expiry_date` is available.

## Eligibility Filter

An option row is eligible when:

```text
0.25 <= abs(option_delta) <= 0.75
0 < option_ttm_days < 365
```

These thresholds are configurable.

## Signal Math

For ETF `i` at prediction time `t`, define directional option notional:

```text
d_o = +option_notional    for calls
d_o = -option_notional    for puts
```

The recent imbalance is:

```text
I_i(t) = sum d_o
```

where the sum is over eligible options in:

```text
(t - 28 calendar days, t)
```

The standardized signal is:

```text
S_i(t) = I_i(t) / (sigma_i(t) + epsilon)
```

where `sigma_i(t)` is the trailing volatility of daily option imbalance.

The default volatility mode is:

```text
rolling_imbalance
```

That means the scale is estimated from trailing daily 28-day rolling imbalances.
The alternate supported mode is:

```text
daily_flow
```

That means the scale is estimated from daily call-minus-put flow.

## Output Columns

Default prefix:

```text
etf_options_positioning_28d
```

Outputs:

```text
<prefix>_signal
<prefix>_observed_imbalance
<prefix>_volatility_scale
<prefix>_observation_count
<prefix>_last_observation_timestamp
<prefix>_staleness_seconds
<prefix>_quality_flag
```

## Missing-Data Behavior

If options positioning data are unavailable, the signal is `NaN`.
The quality flag states the reason.

Missing data are not replaced with zero.

## Difference From RFQ Flow Alphas

RFQ and TRACE flow alphas measure actual bond inquiry or trade flow.
This signal measures listed options positioning on a fixed-income ETF.

It can be used as a market or ETF-level sentiment/risk-demand input.
It should not be treated as a direct bond-level signal unless an ETF-to-bond mapping is defined separately.

## Tests

Covered by:

```text
bond_alpha/tests/test_etf_options_positioning.py
```
