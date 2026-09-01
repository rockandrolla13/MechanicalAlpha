"""Frozen triplet scoring and aggregation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


def frozen_rank_transform(values: pd.Series, train_values: pd.Series) -> pd.Series:
    """Map values to normal scores using train-period empirical ranks."""

    train = pd.to_numeric(train_values, errors="coerce").dropna().sort_values(kind="mergesort").to_numpy(dtype=float)
    values_clean = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    if train.size == 0:
        return pd.Series(np.nan, index=values.index)
    ranks = np.searchsorted(train, values_clean, side="right")
    probs = np.clip((ranks + 0.5) / (train.size + 1.0), 1.0e-6, 1.0 - 1.0e-6)
    return pd.Series(norm.ppf(probs), index=values.index)


def score_triplet(panel: pd.DataFrame, selected: pd.DataFrame, *, train_panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Score selected triplet components from frozen train-selected definitions."""

    if panel.empty or selected.empty:
        return pd.DataFrame(columns=["clock_index", "component", "score"])
    train_panel = panel if train_panel is None else train_panel
    selected_only = selected[selected.get("selected", True).astype(bool)].copy()
    rows: list[pd.DataFrame] = []
    keys = ["lag", "anchor", "horizon", "target_type"]
    for triplet in selected_only.itertuples(index=False):
        mask = np.ones(len(panel), dtype=bool)
        train_mask = np.ones(len(train_panel), dtype=bool)
        parts = []
        for key in keys:
            value = getattr(triplet, key)
            mask &= panel[key].eq(value).to_numpy()
            train_mask &= train_panel[key].eq(value).to_numpy()
            parts.append(f"{key}={value}")
        subset = panel.loc[mask].copy()
        if subset.empty:
            continue
        sign = 1.0 if float(getattr(triplet, "rho")) >= 0 else -1.0
        subset["component"] = "|".join(parts)
        subset["score"] = sign * frozen_rank_transform(subset["past_move"], train_panel.loc[train_mask, "past_move"])
        rows.append(subset[["clock_index", "timestamp", "bond_id", "component", "score"] if "bond_id" in subset.columns else ["clock_index", "timestamp", "component", "score"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["clock_index", "component", "score"])


def aggregate_triplet_signals(scores: pd.DataFrame, *, weight_col: str | None = None) -> pd.DataFrame:
    """Aggregate component scores into one triplet signal per clock row."""

    if scores.empty:
        return pd.DataFrame(columns=["clock_index", "triplet_signal", "component_count"])
    group_cols = ["clock_index"]
    for optional in ("timestamp", "bond_id"):
        if optional in scores.columns:
            group_cols.append(optional)
    rows: list[dict[str, object]] = []
    for key, group in scores.groupby(group_cols, sort=True):
        weights = np.ones(len(group)) if weight_col is None or weight_col not in group.columns else pd.to_numeric(group[weight_col], errors="coerce").fillna(0.0).to_numpy()
        values = pd.to_numeric(group["score"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
        denom = float(np.sum(np.abs(weights)))
        signal = np.nan if denom == 0 else float(np.sum(weights * values) / denom)
        key_tuple = key if isinstance(key, tuple) else (key,)
        rows.append({**dict(zip(group_cols, key_tuple, strict=True)), "triplet_signal": signal, "component_count": int(len(group))})
    return pd.DataFrame(rows)

