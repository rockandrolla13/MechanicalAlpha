# A16 RFQ Scarcity and Disagreement

## Signal

A16 measures weak dealer response and quote disagreement in RFQ data.

The raw state includes:

- latest responder count;
- response scarcity;
- dealer count;
- quote dispersion;
- response latency;
- executable indication age;
- no-response rate;
- firm-up rate;
- execution rate.

## Fitted Model

A16 fits logistic models on training rows only.

Supported targets are:

- responded;
- firmed up;
- executed.

If there are too few observations or only one target class, the model falls back to the train-period base rate.

## Windows

Fast windows:

```text
1d, 3d, last 5 RFQs, last 10 RFQs
```

Slow windows:

```text
5d, 10d, 20d, 40d, 60d, 120d, last 25 RFQs, last 50 RFQs
```

The slow model is intended to be refit monthly.

## Point-In-Time Rules

Only RFQs before the prediction timestamp enter the state.

Validation and test scoring use frozen train-period feature means, scales, and coefficients.

Future firm-up, response, or execution status must not be used before it is known.

## Missing-Data Behavior

If response counts, quote dispersion, latency, or RFQ decision flags are absent, the corresponding fields are `NaN`.

TRACE-only data will degrade because this is an RFQ-specific alpha.

## Economic Interpretation

High scarcity or disagreement means liquidity is weak and execution uncertainty is high.

This alpha should be used as a liquidity-quality and toxicity input, not as a direct clean-price return signal without separate validation.
