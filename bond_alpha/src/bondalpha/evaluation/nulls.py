"""Negative-control checks from public data."""

from __future__ import annotations

import pandas as pd


def null_feature_correlation(features: pd.DataFrame, labels: pd.DataFrame, target_column: str) -> dict[str, float]:
    merged = features.merge(labels[["event_id", target_column]], on="event_id", how="inner").dropna()
    controls = [c for c in merged.columns if c.endswith("_control")]
    return {name: float(merged[name].corr(merged[target_column])) for name in controls if merged[name].nunique() > 1}
