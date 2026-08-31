"""Predictive evaluation from public labels."""

from __future__ import annotations

import pandas as pd
from sklearn.metrics import roc_auc_score

from bondalpha.models.calibration import probability_metrics


def evaluate_predictions(labels: pd.DataFrame, predictions: pd.DataFrame, target_column: str) -> dict[str, float]:
    merged = labels[["event_id", target_column, "split"]].merge(predictions, on="event_id", how="inner")
    test = merged[merged["split"].isin(["validation", "test"]) & merged[target_column].notna()]
    if test.empty:
        return {"rows": 0, "auc": float("nan"), "log_loss": float("nan"), "brier": float("nan")}
    metrics = probability_metrics(test[target_column], test["prediction"])
    metrics["rows"] = int(len(test))
    metrics["auc"] = float(roc_auc_score(test[target_column].astype(int), test["prediction"])) if test[target_column].nunique() > 1 else float("nan")
    return metrics
