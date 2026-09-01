"""Matched-clock diagnostics for triplet signals."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def evaluate_clock_transfer(signal: pd.DataFrame, returns: pd.DataFrame, *, on: tuple[str, ...] = ("clock_index",)) -> pd.DataFrame:
    """Compare signal and forward return on a matched opportunity set."""

    if signal.empty or returns.empty:
        return pd.DataFrame([{"n_obs": 0, "spearman": np.nan, "pearson": np.nan}])
    merged = signal.merge(returns, on=list(on), how="inner")
    clean = merged[["triplet_signal", "future_return"]].dropna()
    if len(clean) < 3:
        return pd.DataFrame([{"n_obs": int(len(clean)), "spearman": np.nan, "pearson": np.nan}])
    return pd.DataFrame(
        [
            {
                "n_obs": int(len(clean)),
                "spearman": float(spearmanr(clean["triplet_signal"], clean["future_return"]).statistic),
                "pearson": float(clean["triplet_signal"].corr(clean["future_return"])),
            }
        ]
    )

