"""Naive alpha baselines."""

from __future__ import annotations

import pandas as pd


def unconditional_probability(labels: pd.Series) -> float:
    valid = labels.dropna().astype(float)
    return float(valid.mean()) if len(valid) else 0.5
