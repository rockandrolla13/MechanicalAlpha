"""Liquidity rank mapping and calibration."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from bondsim.config import LiquidityConfig


def target_rates_from_ranks(bonds: pd.DataFrame, config: LiquidityConfig) -> pd.Series:
    n = max(len(bonds), 1)
    ranks = ((bonds["liquidity_rank_global"].rank(method="first") - 0.5) / n).clip(1e-4, 1 - 1e-4)
    sigma = np.log(config.target_median_events_per_day / config.target_p10_events_per_day) / abs(norm.ppf(0.10))
    rates = np.exp(np.log(config.target_median_events_per_day) + sigma * norm.ppf(ranks))
    return pd.Series(np.minimum(rates, config.maximum_events_per_day), index=bonds.index)


def realized_rate_summary(events: pd.DataFrame, n_sessions: int) -> dict[str, float]:
    rates = events.groupby("synthetic_bond_id")["event_id"].count() / max(n_sessions, 1)
    if rates.empty:
        return {"median": 0.0, "p10": 0.0, "max": 0.0}
    return {
        "median": float(rates.quantile(0.50)),
        "p10": float(rates.quantile(0.10)),
        "max": float(rates.max()),
    }
