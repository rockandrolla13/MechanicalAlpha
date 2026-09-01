"""Shared portfolio primitives from the cookbook."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BlockedStrategy:
    """A typed unavailable strategy result."""

    strategy_id: str
    status: str
    reason: str
    blocking_decisions: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()


def _as_series(values: pd.Series | dict[str, float], *, name: str) -> pd.Series:
    series = values if isinstance(values, pd.Series) else pd.Series(values, dtype=float)
    return pd.to_numeric(series, errors="coerce").astype(float).rename(name)


def _normalize_gross(weights: pd.Series, gross: float) -> pd.Series:
    denominator = float(weights.abs().sum())
    if denominator <= 0 or not np.isfinite(denominator):
        return weights * np.nan
    return weights * (float(gross) / denominator)


def _apply_eligibility(signal: pd.Series, eligible: pd.Series | None) -> pd.Series:
    if eligible is None:
        return signal
    mask = eligible.reindex(signal.index).fillna(False).astype(bool)
    return signal.where(mask)


def inverse_volatility_sign_weights(
    signal: pd.Series,
    volatility: pd.Series,
    *,
    eligible: pd.Series | None = None,
    gross: float = 1.0,
) -> pd.Series:
    """Construct sign weights scaled by inverse volatility."""

    signal = _apply_eligibility(_as_series(signal, name="signal"), eligible)
    volatility = _as_series(volatility, name="volatility").reindex(signal.index)
    raw = np.sign(signal) / volatility.replace(0.0, np.nan)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _normalize_gross(raw, gross)


def signal_proportional_weights(
    signal: pd.Series,
    volatility: pd.Series | None = None,
    *,
    eligible: pd.Series | None = None,
    vol_power: float = 0.0,
    gross: float = 1.0,
) -> pd.Series:
    """Construct weights proportional to signal, optionally volatility scaled."""

    signal = _apply_eligibility(_as_series(signal, name="signal"), eligible)
    raw = signal.copy()
    if volatility is not None and vol_power != 0.0:
        volatility = _as_series(volatility, name="volatility").reindex(signal.index)
        raw = raw / volatility.replace(0.0, np.nan).pow(vol_power)
    raw = raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return _normalize_gross(raw, gross)


def equal_weight_rank_halves(signal: pd.Series, *, eligible: pd.Series | None = None, gross: float = 1.0) -> pd.Series:
    """Long the top half and short the bottom half with equal absolute weights."""

    original_index = signal.index
    signal = _apply_eligibility(_as_series(signal, name="signal"), eligible).dropna()
    weights = pd.Series(0.0, index=original_index)
    if len(signal) < 2:
        return weights * np.nan
    ranks = signal.rank(method="first")
    midpoint = (len(signal) + 1) / 2.0
    weights.loc[ranks.index[ranks > midpoint]] = 1.0
    weights.loc[ranks.index[ranks < midpoint]] = -1.0
    return _normalize_gross(weights, gross)


def linear_rank_halves(signal: pd.Series, *, eligible: pd.Series | None = None, gross: float = 1.0) -> pd.Series:
    """Construct dollar-neutral weights proportional to centered ranks."""

    original_index = signal.index
    signal = _apply_eligibility(_as_series(signal, name="signal"), eligible).dropna()
    if signal.empty:
        return pd.Series(0.0, index=original_index)
    ranks = signal.rank(method="average")
    centered = ranks - ranks.mean()
    weights = pd.Series(0.0, index=original_index)
    weights.loc[signal.index] = _normalize_gross(centered, gross)
    return weights


def project_beta_neutral(weights: pd.Series, beta: pd.Series, *, gross: float | None = None) -> pd.Series:
    """Project weights onto the zero-beta subspace."""

    weights = _as_series(weights, name="weights")
    beta = _as_series(beta, name="beta").reindex(weights.index).fillna(0.0)
    denominator = float((beta * beta).sum())
    if denominator <= 0:
        projected = weights.copy()
    else:
        projected = weights - beta * float((weights * beta).sum()) / denominator
    return _normalize_gross(projected, gross) if gross is not None else projected


def apply_position_bounds(
    weights: pd.Series,
    *,
    lower: float | pd.Series = -0.05,
    upper: float | pd.Series = 0.05,
    gross: float | None = None,
    max_iterations: int = 20,
) -> pd.Series:
    """Apply symmetric or instrument-specific position bounds."""

    weights = _as_series(weights, name="weights")
    lower_s = pd.Series(lower, index=weights.index, dtype=float) if np.isscalar(lower) else _as_series(lower, name="lower").reindex(weights.index)
    upper_s = pd.Series(upper, index=weights.index, dtype=float) if np.isscalar(upper) else _as_series(upper, name="upper").reindex(weights.index)
    if gross is None:
        return weights.clip(lower=lower_s, upper=upper_s)
    current = weights.clip(lower=lower_s, upper=upper_s)
    for _ in range(max_iterations):
        before = current.copy()
        current = _normalize_gross(current, gross).clip(lower=lower_s, upper=upper_s)
        if np.allclose(before.to_numpy(dtype=float), current.to_numpy(dtype=float), equal_nan=True):
            break
    return current


def tranche_rebalance(target_weights: pd.DataFrame, *, tranche_count: int) -> pd.DataFrame:
    """Average active tranche target weights through time."""

    if tranche_count <= 0:
        raise ValueError("tranche_count must be positive")
    if target_weights.empty:
        return target_weights.copy()
    ordered = target_weights.sort_index(kind="mergesort")
    tranches = [ordered.shift(i).fillna(0.0) for i in range(tranche_count)]
    return sum(tranches) / float(tranche_count)
