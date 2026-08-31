"""Common feature utilities for standalone alpha files."""

from __future__ import annotations

import numpy as np
import pandas as pd


EPSILON = 1e-9


def ordered(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"])
    return out.sort_values(["scenario", "synthetic_bond_id", "timestamp_utc", "event_id"])


def robust_zscore(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median()
    scale = 1.4826 * mad if mad > 0 else series.std()
    if not np.isfinite(scale) or scale == 0:
        return pd.Series(0.0, index=series.index)
    return (series - median) / scale
