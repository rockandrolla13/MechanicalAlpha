"""Deterministic PnL and risk metric helpers.

All trade quantities are signed. Positive quantity is long risk and negative
quantity is short risk.
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


ArrayLike = float | int | Iterable[float] | pd.Series | np.ndarray


def price_trade_pnl(
    quantity: ArrayLike,
    entry_price: ArrayLike,
    exit_price: ArrayLike,
    *,
    cost: ArrayLike = 0.0,
) -> pd.Series:
    """Return price trade PnL as ``q * (exit - entry) - cost``."""

    q = _as_series(quantity, "quantity")
    entry = _align_like(entry_price, q, "entry_price")
    exit_ = _align_like(exit_price, q, "exit_price")
    trade_cost = _align_like(cost, q, "cost")
    return q * (exit_ - entry) - trade_cost


def credit_spread_pnl(
    quantity: ArrayLike,
    dv01: ArrayLike,
    spread_entry: ArrayLike,
    spread_exit: ArrayLike,
    *,
    cost: ArrayLike = 0.0,
) -> pd.Series:
    """Return spread PnL as ``-q * DV01 * (spread_exit - spread_entry) - cost``."""

    q = _as_series(quantity, "quantity")
    dv01_series = _align_like(dv01, q, "dv01")
    entry = _align_like(spread_entry, q, "spread_entry")
    exit_ = _align_like(spread_exit, q, "spread_exit")
    trade_cost = _align_like(cost, q, "cost")
    return -q * dv01_series * (exit_ - entry) - trade_cost


def mark_to_market_value(
    cash: ArrayLike,
    position: ArrayLike,
    mark_price: ArrayLike,
) -> pd.Series:
    """Return queue account value as ``cash + position * mark_price``."""

    cash_series = _as_series(cash, "cash")
    pos = _align_like(position, cash_series, "position")
    mark = _align_like(mark_price, cash_series, "mark_price")
    return cash_series + pos * mark


def mark_to_market_pnl(
    cash: ArrayLike,
    position: ArrayLike,
    mark_price: ArrayLike,
    *,
    starting_value: float = 0.0,
) -> pd.Series:
    """Return marked PnL relative to a starting account value."""

    return mark_to_market_value(cash, position, mark_price) - float(starting_value)


def daily_pnl(
    pnl: ArrayLike,
    timestamps: ArrayLike,
) -> pd.Series:
    """Aggregate event-level PnL by calendar day."""

    pnl_series = _as_series(pnl, "pnl")
    timestamp_series = _align_index_like(timestamps, pnl_series, "timestamps")
    dates = pd.to_datetime(timestamp_series).dt.normalize()
    return pnl_series.groupby(dates, sort=True).sum()


def signed_exposure(quantity: ArrayLike, mark_price: ArrayLike) -> pd.Series:
    """Return signed marked exposure as ``quantity * mark_price``."""

    q = _as_series(quantity, "quantity")
    mark = _align_like(mark_price, q, "mark_price")
    return q * mark


def gross_exposure(quantity: ArrayLike, mark_price: ArrayLike) -> pd.Series:
    """Return absolute marked exposure."""

    return signed_exposure(quantity, mark_price).abs()


def drawdown(equity_curve: ArrayLike) -> pd.Series:
    """Return drawdown from the running peak as a non-positive series."""

    equity = _as_series(equity_curve, "equity_curve")
    return equity - equity.cummax()


def max_drawdown(equity_curve: ArrayLike) -> float:
    """Return the worst drawdown from the running peak."""

    series = drawdown(equity_curve).dropna()
    if series.empty:
        return math.nan
    return float(series.min())


def runup(equity_curve: ArrayLike) -> pd.Series:
    """Return runup from the running trough as a non-negative series."""

    equity = _as_series(equity_curve, "equity_curve")
    return equity - equity.cummin()


def max_runup(equity_curve: ArrayLike) -> float:
    """Return the largest runup from the running trough."""

    series = runup(equity_curve).dropna()
    if series.empty:
        return math.nan
    return float(series.max())


def volatility(pnl: ArrayLike, *, annualization: float | None = None) -> float:
    """Return sample volatility, optionally scaled by ``sqrt(annualization)``."""

    values = _as_series(pnl, "pnl").dropna()
    if len(values) < 2:
        return math.nan
    vol = float(values.std(ddof=1))
    if annualization is None:
        return vol
    return vol * math.sqrt(float(annualization))


def sharpe_like_ratio(pnl: ArrayLike, *, annualization: float | None = None) -> float:
    """Return mean PnL divided by sample volatility."""

    values = _as_series(pnl, "pnl").dropna()
    if len(values) < 2:
        return math.nan
    vol = float(values.std(ddof=1))
    if vol == 0.0:
        return math.nan
    ratio = float(values.mean()) / vol
    if annualization is None:
        return ratio
    return ratio * math.sqrt(float(annualization))


def profit_factor(pnl: ArrayLike) -> float:
    """Return gross profits divided by absolute gross losses."""

    values = _as_series(pnl, "pnl").dropna()
    gains = float(values[values > 0.0].sum())
    losses = float(values[values < 0.0].sum())
    if losses == 0.0:
        return math.inf if gains > 0.0 else math.nan
    return gains / abs(losses)


def win_rate(pnl: ArrayLike, *, include_zero: bool = False) -> float:
    """Return the fraction of observations with positive PnL."""

    values = _as_series(pnl, "pnl").dropna()
    if not include_zero:
        values = values[values != 0.0]
    if values.empty:
        return math.nan
    return float((values > 0.0).mean())


def pnl_summary(pnl: ArrayLike, *, annualization: float | None = None) -> dict[str, float]:
    """Return a compact deterministic summary of PnL and risk metrics."""

    values = _as_series(pnl, "pnl").dropna()
    equity = values.cumsum()
    return {
        "count": float(len(values)),
        "total_pnl": float(values.sum()) if not values.empty else math.nan,
        "mean_pnl": float(values.mean()) if not values.empty else math.nan,
        "volatility": volatility(values, annualization=annualization),
        "sharpe_like_ratio": sharpe_like_ratio(values, annualization=annualization),
        "profit_factor": profit_factor(values),
        "win_rate": win_rate(values),
        "max_drawdown": max_drawdown(equity),
        "max_runup": max_runup(equity),
    }


def _as_series(values: ArrayLike, name: str) -> pd.Series:
    if isinstance(values, pd.Series):
        return values.astype(float).rename(name)
    if np.isscalar(values):
        return pd.Series([float(values)], name=name)
    return pd.Series(values, dtype=float, name=name)


def _align_like(values: ArrayLike, index_source: pd.Series, name: str) -> pd.Series:
    if isinstance(values, pd.Series):
        series = values.astype(float).rename(name)
        if len(series) == 1 and len(index_source) != 1:
            return pd.Series(float(series.iloc[0]), index=index_source.index, name=name)
        return series.reindex(index_source.index)
    if np.isscalar(values):
        return pd.Series(float(values), index=index_source.index, name=name)
    series = pd.Series(values, dtype=float, name=name)
    if len(series) != len(index_source):
        raise ValueError(f"{name} length {len(series)} does not match {index_source.name} length {len(index_source)}")
    series.index = index_source.index
    return series


def _align_index_like(values: ArrayLike, index_source: pd.Series, name: str) -> pd.Series:
    if isinstance(values, pd.Series):
        series = values.rename(name)
        if len(series) == 1 and len(index_source) != 1:
            return pd.Series(series.iloc[0], index=index_source.index, name=name)
        return series.reindex(index_source.index)
    if np.isscalar(values):
        return pd.Series(values, index=index_source.index, name=name)
    series = pd.Series(values, name=name)
    if len(series) != len(index_source):
        raise ValueError(f"{name} length {len(series)} does not match {index_source.name} length {len(index_source)}")
    series.index = index_source.index
    return series
