"""Simple economic bucket evaluation."""

from __future__ import annotations

import pandas as pd


def bucket_return(labels: pd.DataFrame, predictions: pd.DataFrame, target_column: str) -> pd.DataFrame:
    merged = labels[["event_id", target_column]].merge(predictions, on="event_id", how="inner").dropna()
    if merged.empty:
        return pd.DataFrame(columns=["bucket", "mean_label", "rows"])
    merged["bucket"] = pd.qcut(merged["prediction"], q=min(5, len(merged)), duplicates="drop")
    return merged.groupby("bucket", observed=True)[target_column].agg(mean_label="mean", rows="count").reset_index()
