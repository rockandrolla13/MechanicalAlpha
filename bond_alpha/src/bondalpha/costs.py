"""Transaction-cost assumptions for public alpha research."""

from __future__ import annotations

import pandas as pd


def simple_cost_hurdle(frame: pd.DataFrame, base_price_points: float = 0.03) -> pd.Series:
    """Return a deterministic per-event cost hurdle in price points."""

    liquidity_scale = 1.0 / frame.groupby("synthetic_bond_id")["event_id"].transform("count").clip(lower=1) ** 0.25
    return pd.Series(base_price_points * liquidity_scale, index=frame.index, name="cost_hurdle")
