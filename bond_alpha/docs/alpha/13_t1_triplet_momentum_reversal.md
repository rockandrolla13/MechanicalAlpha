# T1 Triplet Momentum/Reversal

## Signal

T1 searches lag-anchor-horizon triplets on a point-in-time sampled bond state.

For a sampled state `x`:

```text
past_move = x(anchor) - x(anchor - lag)

future_move = x(anchor + horizon) - x(anchor)
```

The method estimates Spearman dependence between `past_move` and `future_move` in training data.

Selected triplets are scored with a frozen train-period rank transform:

```text
score = sign(rho_train) * normal_score_train_rank(past_move)
```

Positive score means positive expected future move under the selected train relationship.

## Clocks

The entry point supports:

- calendar clock;
- event clock;
- information clock.

The information clock requires a nonnegative activity column such as notional, DV01, or CR01.

## Targets

The core triplet code supports:

- clean-price moves;
- spread-implied moves when spread and duration are supplied to the panel builder;
- residual moves when a residual state is supplied as the sampled value.

The standalone `T1` entry point defaults to clean-price because that is the portable public field.

## Selection

Selection uses training data only.

Multiplicity adjustment includes searched candidates that fail to produce enough observations.

The default correction is Holm.

## Point-In-Time Rules

State sampling is a backward as-of join.

Future prices, labels, and truth columns are not inputs.

Changing test-period rows does not change the fitted train selection object.

## Blocked Literal Decisions

The source-literal cookbook momentum strategy still has unresolved PI decisions:

- `MOM-001`;
- `MOM-002`.

T1 is therefore a bond-native triplet operator, not a silent release of the literal FX momentum strategy.
