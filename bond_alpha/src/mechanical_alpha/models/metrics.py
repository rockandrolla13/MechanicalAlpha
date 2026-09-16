"""Model evaluation metrics for event prediction tasks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    log_loss,
    roc_auc_score,
)


@dataclass(frozen=True)
class BinaryClassificationMetrics:
    """Metrics for one binary out-of-sample prediction set."""

    log_loss: float
    brier_score: float
    roc_auc: float
    pr_auc: float
    calibration_intercept: float
    calibration_slope: float
    ece: float
    confusion_matrix: dict[str, int]
    decile_performance: pd.DataFrame


def evaluate_binary_predictions(
    y_true: pd.Series | np.ndarray,
    y_probability: pd.Series | np.ndarray,
    *,
    threshold: float = 0.5,
    n_bins: int = 10,
) -> BinaryClassificationMetrics:
    """Evaluate binary probabilities without assuming both classes are present."""

    y = np.asarray(y_true, dtype=int)
    p = np.clip(np.asarray(y_probability, dtype=float), 1e-12, 1.0 - 1e-12)
    predicted = (p >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predicted, labels=[0, 1]).ravel()

    return BinaryClassificationMetrics(
        log_loss=float(log_loss(y, p, labels=[0, 1])),
        brier_score=float(brier_score_loss(y, p)),
        roc_auc=_safe_score(roc_auc_score, y, p),
        pr_auc=_safe_score(average_precision_score, y, p),
        calibration_intercept=_calibration_intercept_slope(y, p)[0],
        calibration_slope=_calibration_intercept_slope(y, p)[1],
        ece=float(expected_calibration_error(y, p, n_bins=n_bins)),
        confusion_matrix={"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        decile_performance=decile_performance(y, p, n_bins=n_bins),
    )


def expected_calibration_error(y_true: np.ndarray, y_probability: np.ndarray, *, n_bins: int = 10) -> float:
    """Return equal-width expected calibration error."""

    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_probability, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = len(y)
    if total == 0:
        return float("nan")

    error = 0.0
    for idx in range(n_bins):
        lower, upper = edges[idx], edges[idx + 1]
        if idx == n_bins - 1:
            mask = (p >= lower) & (p <= upper)
        else:
            mask = (p >= lower) & (p < upper)
        if not np.any(mask):
            continue
        error += float(np.mean(mask) * abs(np.mean(y[mask]) - np.mean(p[mask])))
    return error


def decile_performance(y_true: np.ndarray, y_probability: np.ndarray, *, n_bins: int = 10) -> pd.DataFrame:
    """Summarize realized event rate by predicted-probability bucket."""

    frame = pd.DataFrame({"target": np.asarray(y_true, dtype=int), "probability": np.asarray(y_probability)})
    if frame.empty:
        return pd.DataFrame(columns=["bucket", "row_count", "mean_probability", "event_rate"])

    ranks = frame["probability"].rank(method="first")
    frame["bucket"] = pd.qcut(ranks, q=min(n_bins, len(frame)), labels=False, duplicates="drop") + 1
    return (
        frame.groupby("bucket", observed=True)
        .agg(
            row_count=("target", "size"),
            mean_probability=("probability", "mean"),
            event_rate=("target", "mean"),
        )
        .reset_index()
    )


def _safe_score(function, y_true: np.ndarray, y_probability: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(function(y_true, y_probability))


def _calibration_intercept_slope(y_true: np.ndarray, y_probability: np.ndarray) -> tuple[float, float]:
    if len(np.unique(y_true)) < 2:
        return float("nan"), float("nan")
    logits = np.log(y_probability / (1.0 - y_probability)).reshape(-1, 1)
    model = LogisticRegression(C=1e6, solver="lbfgs")
    model.fit(logits, y_true)
    return float(model.intercept_[0]), float(model.coef_[0][0])
