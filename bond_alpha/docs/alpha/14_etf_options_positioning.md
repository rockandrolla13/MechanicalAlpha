# ETF Options Positioning

## Signal

This alpha adapts options-positioning pressure to fixed-income ETFs and to constituent bonds through ETF lookthrough weights.

It computes three standalone component signals:

```text
oi_change =
    sum(call_oi_change * option_notional)
  - sum(put_oi_change * option_notional)

volume_pressure =
    sum(call_volume * option_notional)
  - sum(put_volume * option_notional)

dealer_greeks =
    sum(dealer_delta_exposure + dealer_gamma_exposure + dealer_vega_exposure)
```

If direct dealer greek exposure is unavailable, `dealer_greeks` falls back to a documented chain-derived estimate from option delta, gamma, open interest, and option notional. The quality flag records that fallback.

The composite signal is the simple mean of finite component signals. It is not fitted.

The legacy COFFEE-compatible signal remains available:

```text
legacy_signal =
    rolling_sum(call_notional - put_notional)
  / trailing_volatility(call_notional - put_notional)
```

Positive values mean upside ETF option pressure under the call-positive and put-negative convention.

## Required Inputs

ETF-native signals consume point-in-time rows in `external_factors`:

```text
factor_id = etf_option_position
timestamp
publication_timestamp
asset_id or etf_ticker
option_type
option_delta
option_ttm_days
option_notional
open_interest
previous_open_interest or oi_change
option_volume
dealer_delta_exposure
dealer_gamma_exposure
dealer_vega_exposure
```

Bond-lookthrough signals also consume:

```text
factor_id = etf_bond_lookthrough_weight
timestamp
publication_timestamp
asset_id
bond_id
value
weight_type
```

The default `weight_type` is `cr01`.

## Point-In-Time Rules

Option rows must satisfy:

```text
timestamp < prediction_timestamp
publication_timestamp <= prediction_timestamp
```

Lookthrough rows must satisfy the same cutoff rule.

The latest available lookthrough weight is used for each ETF-bond pair.

Expiring or out-of-delta-band options are excluded.

No simulator truth or latent state is used.

## Missing Data

If ETF options data are unavailable, the alpha emits `NaN` and an explicit quality flag.

If lookthrough weights are unavailable, ETF-native signals still compute and bond-lookthrough signals are `NaN`.

The alpha does not fabricate positioning from ETF price, flow, or bond TRACE activity.

## Outputs

For each configured window, default `5D`, `20D`, and `60D`, the module emits:

```text
etf_options_<window>_oi_change_signal
etf_options_<window>_volume_pressure_signal
etf_options_<window>_dealer_greeks_signal
etf_options_<window>_composite_signal
etf_options_<window>_<component>_bond_lookthrough_signal
```

Each component also emits observation counts, last observation timestamps, and quality flags.

## Interpretation

Open-interest change is the slower positioning signal.

Volume pressure is the faster option-flow signal.

Dealer greek exposure is the hedging-pressure signal.

The bond-lookthrough version asks whether ETF option pressure spills into constituent bonds through ETF holdings or risk weights.
