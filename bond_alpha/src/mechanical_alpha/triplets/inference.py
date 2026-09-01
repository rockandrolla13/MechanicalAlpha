"""Triplet estimation, multiplicity adjustment, and train-only selection."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True)
class TripletEstimate:
    """One fitted lag-anchor-horizon estimate."""

    lag: int
    anchor: int
    horizon: int
    target_type: str
    rho: float
    p_value: float
    n_obs: int
    adjusted_p_value: float | None = None
    selected: bool = False


def estimate_triplet_family(panel: pd.DataFrame, *, group_cols: tuple[str, ...] = ("lag", "anchor", "horizon", "target_type")) -> pd.DataFrame:
    """Estimate Spearman dependence for every searched triplet candidate."""

    if panel.empty:
        return pd.DataFrame(columns=[*group_cols, "rho", "p_value", "n_obs"])
    rows: list[dict[str, object]] = []
    for key, group in panel.groupby(list(group_cols), dropna=False, sort=True):
        clean = group[["past_move", "future_move"]].dropna()
        if len(clean) < 3 or clean["past_move"].nunique() < 2 or clean["future_move"].nunique() < 2:
            rho, p_value = np.nan, 1.0
        else:
            stat = spearmanr(clean["past_move"], clean["future_move"])
            rho = float(stat.statistic)
            p_value = float(stat.pvalue) if np.isfinite(stat.pvalue) else 1.0
        key_tuple = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(group_cols, key_tuple, strict=True)), "rho": rho, "p_value": p_value, "n_obs": int(len(clean))})
    return pd.DataFrame(rows)


def adjust_triplet_multiplicity(estimates: pd.DataFrame, *, method: str = "holm") -> pd.DataFrame:
    """Add adjusted p-values for all searched triplets."""

    frame = estimates.copy()
    if frame.empty:
        frame["adjusted_p_value"] = []
        return frame
    pvals = pd.to_numeric(frame["p_value"], errors="coerce").fillna(1.0).clip(0.0, 1.0).to_numpy(dtype=float)
    order = np.argsort(pvals)
    adjusted = np.ones_like(pvals)
    m = len(pvals)
    if method == "holm":
        running = 0.0
        for rank, idx in enumerate(order):
            value = min(1.0, (m - rank) * pvals[idx])
            running = max(running, value)
            adjusted[idx] = running
    elif method in {"bh", "fdr_bh"}:
        running = 1.0
        for rank, idx in reversed(list(enumerate(order, start=1))):
            running = min(running, pvals[idx] * m / rank)
            adjusted[idx] = min(1.0, running)
    else:
        raise ValueError(f"unknown multiplicity method: {method}")
    frame["adjusted_p_value"] = adjusted
    return frame


def select_triplets(estimates: pd.DataFrame, *, alpha: float = 0.05, min_obs: int = 20) -> pd.DataFrame:
    """Mark selected triplets using train-period estimates only."""

    frame = estimates.copy()
    if "adjusted_p_value" not in frame.columns:
        frame = adjust_triplet_multiplicity(frame)
    frame["selected"] = (frame["adjusted_p_value"] <= alpha) & (frame["n_obs"] >= min_obs) & frame["rho"].notna()
    return frame

