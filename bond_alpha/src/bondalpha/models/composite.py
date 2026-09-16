"""Composite model helpers."""

from __future__ import annotations

import pandas as pd


def blend_predictions(predictions: list[pd.Series]) -> pd.Series:
    if not predictions:
        raise ValueError("at least one prediction series is required")
    return pd.concat(predictions, axis=1).mean(axis=1).rename("prediction")
