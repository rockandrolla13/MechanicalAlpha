"""Price momentum cookbook operators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.fx_cookbook.common import BlockedStrategy, equal_weight_rank_halves, inverse_volatility_sign_weights


def compute_total_return_momentum_signal(prices: pd.DataFrame, *, lookback: int, denominator: str = "level") -> pd.DataFrame:
    """Compute source-literal momentum on a price-like panel."""

    if lookback <= 0:
        raise ValueError("lookback must be positive")
    if denominator not in {"level", "absolute", "none"}:
        raise ValueError("denominator must be one of: level, absolute, none")
    past = prices.shift(lookback)
    change = prices - past
    if denominator == "none":
        return change
    denom = past.abs() if denominator == "absolute" else past
    return change / denom.replace(0.0, np.nan)


def apply_momentum_hysteresis(signal: pd.DataFrame, previous_position: pd.DataFrame, *, enter: float, exit: float) -> pd.DataFrame:
    """Apply explicit enter/exit thresholds to a momentum signal."""

    if exit > enter:
        raise ValueError("exit threshold cannot exceed enter threshold")
    desired = pd.DataFrame(0.0, index=signal.index, columns=signal.columns)
    desired[signal > enter] = 1.0
    desired[signal < -enter] = -1.0
    hold = signal.abs() >= exit
    aligned_prev = previous_position.reindex_like(signal).fillna(0.0)
    return desired.where(desired != 0.0, aligned_prev.where(hold, 0.0))


def scale_by_signal_dispersion(signal: pd.DataFrame, *, min_dispersion: float = 1.0e-12) -> pd.DataFrame:
    """Scale each row by cross-sectional signal dispersion."""

    dispersion = signal.std(axis=1, ddof=1).replace(0.0, np.nan).clip(lower=min_dispersion)
    return signal.div(dispersion, axis=0)


def residualize_fx_returns(returns: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Residualize returns against contemporaneous factors using OLS per asset."""

    if returns.empty or factors.empty:
        return returns.copy()
    x = np.column_stack([np.ones(len(factors)), factors.to_numpy(dtype=float)])
    residuals = {}
    for column in returns.columns:
        y = pd.to_numeric(returns[column], errors="coerce").to_numpy(dtype=float)
        valid = np.isfinite(y) & np.isfinite(x).all(axis=1)
        if valid.sum() <= x.shape[1]:
            residuals[column] = pd.Series(np.nan, index=returns.index)
            continue
        beta = np.linalg.lstsq(x[valid], y[valid], rcond=None)[0]
        residuals[column] = y - x @ beta
    return pd.DataFrame(residuals, index=returns.index)


def build_time_series_momentum_weights(signal: pd.DataFrame, volatility: pd.DataFrame) -> pd.DataFrame:
    """Build inverse-volatility sign weights row by row."""

    return pd.DataFrame(
        [inverse_volatility_sign_weights(signal.loc[idx], volatility.loc[idx]) for idx in signal.index],
        index=signal.index,
    )


def build_cross_sectional_momentum_weights(signal: pd.DataFrame) -> pd.DataFrame:
    """Build equal-weight rank-half weights row by row."""

    return pd.DataFrame([equal_weight_rank_halves(signal.loc[idx]) for idx in signal.index], index=signal.index)


def blocked_literal_momentum() -> BlockedStrategy:
    """Return source ambiguity blockers for literal cookbook momentum."""

    return BlockedStrategy(
        strategy_id="FX_PRICE_MOMENTUM_LITERAL",
        status="BLOCKED_HUMAN",
        reason="Literal FX momentum requires PI choices for lookback set, denominator, and hysteresis.",
        blocking_decisions=("MOM-001", "MOM-002"),
    )

