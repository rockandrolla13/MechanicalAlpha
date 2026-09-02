# A5 Activity Surprise

## Signal

A5 asks whether activity is abnormal versus a fitted normal baseline.

It is not a simple count feature.

For each bond, issuer, source, event type, clock, and window:

```text
count_surprise = observed_count - expected_count

standardized_count_surprise =
    (observed_count - expected_count) / fitted_residual_scale
```

For risk and size measures:

```text
standardized_measure_surprise =
    (observed_measure - expected_measure) / fitted_residual_scale
```

The supported measures are:

- notional;
- signed notional;
- gross DV01;
- signed DV01;
- gross CR01;
- signed CR01.

## Fitted Baseline

The baseline is fitted on the training period only.

The first attempted model for event counts is a Poisson GLM over:

- hour;
- weekday;
- liquidity bucket;
- rating bucket;
- sector;
- maturity bucket.

If the GLM is too sparse or unstable, A5 falls back to a hierarchical empirical baseline.

The fallback pools in this order:

```text
bond -> issuer -> liquidity bucket -> rating x sector x maturity -> global
```

The fitted artifact stores expected values and fitted residual scales.

## Clocks And Windows

Calendar windows:

```text
1d, 3d, 5d, 10d, 20d, 40d, 60d, 120d
```

RFQ event windows:

```text
last 5, 10, 25, 50 RFQs
```

Trade event windows:

```text
last 5, 10, 25, 50 trades
```

Fast windows are `1d`, `3d`, `5`, and `10`.

Slow windows are `5d` through `120d`, `25`, and `50`.

The slow model is intended to be refit monthly.

## Sources And Event Types

A5 scores:

- RFQ inquiries;
- RFQ firm-ups;
- RFQ executions;
- TRACE trades with valid side.

RFQ and TRACE are kept separate.

## Issuer Comparison

A5 also compares bond activity with issuer activity:

```text
bond_share = observed_bond_activity / observed_issuer_activity

share_surprise = bond_share - expected_bond_share
```

This answers whether activity is concentrated in one bond or broad across the issuer curve.

## Point-In-Time Rules

Only events strictly before the prediction timestamp enter a window.

Fitted baselines use training rows only.

Validation and test rows are scored with frozen fitted parameters.

Changing test-period activity cannot change fitted baselines.

Truth columns, future prices, future fair values, and labels are not inputs.

## Risk Units

Event-level DV01 and CR01 are treated as traded risk.

Static bond DV01 or CR01 is not treated as traded risk unless an explicit unit policy is configured.

This prevents a bond-level risk number from being silently mapped into a trade-level risk amount.

## Economic Interpretation

Positive surprise means activity or risk transfer is higher than normal for the current bond, issuer, bucket, and time context.

A positive signed CR01 surprise means customer-buy credit-risk demand is above normal.

A positive issuer surprise means the whole issuer is unusually active, not only the bond being scored.
