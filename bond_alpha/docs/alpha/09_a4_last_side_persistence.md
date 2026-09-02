# A4 Last-Side Persistence and Switching State

## Signal

A4 measures whether recent RFQ or TRACE side state predicts the next side and future signed CR01 flow.

The raw state includes:

- last observed side;
- same-side run length;
- time since the last side change;
- fraction of the last `N` events matching the latest side;
- switching hazard over the last `N` events;
- signed CR01 imbalance over the last `N` events.

The canonical sign convention is:

```text
1 = customer buy
-1 = customer sell
```

## Fitted Model

A4 now has two simple fitted heads.

Next-side model:

```text
P(next side is customer buy | X_t) = logistic(beta_0 + beta' X_t)
```

Future signed CR01-flow model:

```text
E[future signed CR01 flow over h | X_t] = alpha_0 + alpha' X_t
```

`X_t` contains only A4 state variables observed before the prediction timestamp, plus hour and weekday controls.

## Windows

Fast event windows:

```text
last 5, last 10 RFQs or trades
```

Slow event windows:

```text
last 25, last 50 RFQs or trades
```

The slow model is intended to be refit monthly.

## Targets

The alpha fits separate targets for:

- next RFQ side;
- next TRACE side when side is valid;
- future signed RFQ CR01 flow over `1d` and `3d`;
- future signed TRACE CR01 flow over `1d` and `3d`.

RFQ and TRACE are not combined unless explicitly configured.

## Point-In-Time Safeguards

Fit uses training rows only.

Training targets are censored at the training cutoff. A training row near the split cannot use a validation or test event as its next-side or future-flow target.

Validation and test scoring use frozen coefficients, frozen feature means, and frozen feature scales.

If event-level CR01 is missing, CR01-flow fitted scores are unavailable. The implementation does not substitute static bond CR01 as traded risk.

## Missing-Data Behavior

Raw state values are `NaN` when no prior valid-side observations exist.

The next-side fitted model falls back to the train-period side base rate when there are too few observations or only one target class.

The future-flow fitted model falls back to the train-period mean target when there are too few usable observations.

## Economic Interpretation

A higher next-side score means a higher fitted probability that the next event is a customer buy.

A higher signed-flow score means higher expected future customer-buy CR01 flow.

This is a flow-state alpha. It should be evaluated separately from clean-price return alphas and dealer-toxicity labels.
