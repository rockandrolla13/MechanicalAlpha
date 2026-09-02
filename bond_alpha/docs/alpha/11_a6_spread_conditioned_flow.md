# A6 Spread-Conditioned Flow Pressure

## Signal

A6 asks whether signed flow pressure matters more when liquidity is weak.

The raw flow term is:

```text
flow_pressure =
    sum(side_j * abs(measure_j)) / sum(abs(measure_j))
```

where `measure` is usually notional or CR01.

The alpha then interacts flow with as-of liquidity state:

- composite spread;
- spread percentile;
- bid/ask asymmetry;
- composite disagreement;
- composite staleness.

## Fitted Model

A6 fits simple linear models on training rows only.

Supported targets are:

- future clean-price move;
- future issuer-residual move.

The default model is ridge regression.

Elastic net is available as an explicit config choice.

## Windows

Fast windows:

```text
1d, 3d, last 5 trades, last 10 trades
```

Slow windows:

```text
5d, 10d, 20d, 40d, 60d, 120d, last 25 trades, last 50 trades
```

The slow model is intended to be refit monthly.

## Point-In-Time Rules

Only quote snapshots before the prediction timestamp are used.

Only flow events before the prediction timestamp are used.

Validation and test scoring use frozen train-period feature means, scales, and coefficients.

If CR01 is missing at event level, CR01 flow features are marked missing rather than replaced with static bond risk.

## Economic Interpretation

A large positive score means customer-buy flow pressure is unusually important under the current liquidity state.

This is not a pure flow imbalance alpha.

It is a conditional alpha: the same flow can matter differently when spreads are wide, quotes are stale, or composite sources disagree.
