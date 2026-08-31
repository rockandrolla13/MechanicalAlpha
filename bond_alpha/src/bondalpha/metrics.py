"""Alpha Factory metric helpers."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


def directional_accuracy(labels: pd.Series, scores: pd.Series) -> dict[str, Any]:
    """Score sign agreement while preserving missing-label censorship."""

    valid = labels.notna() & scores.notna()
    if int(valid.sum()) == 0:
        return {"n": 0, "accuracy": math.nan}
    correct = ((labels[valid] > 0) == (scores[valid] > 0)).mean()
    return {"n": int(valid.sum()), "accuracy": float(correct)}


def coverage_by_group(frame: pd.DataFrame, group: str, label: str) -> pd.DataFrame:
    """Return label coverage by one public grouping column."""

    if group not in frame.columns:
        return pd.DataFrame(columns=[group, "rows", "label_coverage"])
    return (
        frame.groupby(group, dropna=False)[label]
        .agg(rows="size", label_coverage=lambda s: float(s.notna().mean()))
        .reset_index()
    )
