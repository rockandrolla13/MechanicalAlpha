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


def estimate_triplet_family(
    panel: pd.DataFrame,
    *,
    group_cols: tuple[str, ...] = ("lag", "anchor", "horizon", "target_type"),
    theta_registry: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Estimate Spearman dependence for every searched triplet candidate."""

    if panel.empty and theta_registry is None:
        return pd.DataFrame(columns=[*group_cols, "rho", "p_value", "n_obs", "effective_n"])
    rows: list[dict[str, object]] = []
    if theta_registry is None:
        candidates = panel[list(group_cols)].drop_duplicates().sort_values(list(group_cols), kind="mergesort")
    else:
        candidates = theta_registry[list(group_cols)].drop_duplicates().sort_values(list(group_cols), kind="mergesort")
    for candidate in candidates.to_dict("records"):
        if panel.empty:
            group = panel
        else:
            mask = pd.Series(True, index=panel.index)
            for column in group_cols:
                mask &= panel[column].eq(candidate[column])
            group = panel.loc[mask]
        clean = group[["past_move", "future_move"]].dropna() if not group.empty else pd.DataFrame(columns=["past_move", "future_move"])
        if len(clean) < 3 or clean["past_move"].nunique() < 2 or clean["future_move"].nunique() < 2:
            rho, p_value = np.nan, 1.0
        else:
            stat = spearmanr(clean["past_move"], clean["future_move"])
            rho = float(stat.statistic)
            p_value = float(stat.pvalue) if np.isfinite(stat.pvalue) else 1.0
        rows.append({**candidate, "rho": rho, "p_value": p_value, "n_obs": int(len(clean)), "effective_n": int(len(clean))})
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
