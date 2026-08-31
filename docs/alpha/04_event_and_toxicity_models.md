# 04 Event And Toxicity Models

This stage adds predictive model scaffolding only.

It does not connect predictions to an RFQ responder.
It does not implement feature formulas.
It expects a prebuilt modeling frame with point-in-time safe features and labels.

## Scope

Supported binary task families:

- next event side
- marked aggressiveness
- first meaningful fair-value move
- anonymous dealer toxicity

Every task must name:

- prediction timestamp column
- target column
- feature columns
- optional label timestamp column
- optional feature timestamp columns
- optional last-side benchmark column
- optional imbalance benchmark column

## Point-In-Time Rule

The model layer rejects a row when any configured feature timestamp is later than the prediction timestamp.

If a label timestamp is supplied, it must be strictly after the prediction timestamp.

The model layer does not decide whether a field is economically valid.
That belongs in the label factory and feature registry.

## Benchmarks

The scaffold supports:

- unconditional event frequency
- last-side conditional frequency
- imbalance-only logistic benchmark

These are always evaluated out of sample on the test period.

## Models

The scaffold supports:

- L2-regularized logistic regression
- gradient-boosted trees

Logistic regression is the default primary model for next-side and first-move tasks.
Gradient boosting is available for toxicity and aggressiveness baselines.

## Evaluation

Metrics include:

- log loss
- Brier score
- ROC AUC
- precision-recall AUC
- calibration intercept
- calibration slope
- expected calibration error
- confusion matrix
- decile performance

Splits are chronological.
Random row splitting is not used.

## Required Inputs

The implementation is generic DataFrame code.

It does not import:

- marketdb
- simulator internals
- factor implementations
- RFQ responder code

The expected handoff is:

```text
point-in-time features + labels
  -> ModelTask
  -> evaluate_task
  -> benchmark/model predictions and metrics
```

## Current Limitations

This is scaffolding.

It does not yet:

- build labels
- build features
- train final production models
- produce persisted prediction artifacts
- run monthly stability reports
- optimize dealer response policy
