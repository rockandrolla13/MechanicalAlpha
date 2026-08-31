"""Stability summaries by month."""

from __future__ import annotations

import pandas as pd


def monthly_prediction_stability(predictions: pd.DataFrame) -> pd.DataFrame:
    out = predictions.copy()
    out["month"] = pd.to_datetime(out["timestamp_utc"]).dt.to_period("M").astype(str)
    return out.groupby("month")["prediction"].agg(mean="mean", std="std", rows="count").reset_index()
