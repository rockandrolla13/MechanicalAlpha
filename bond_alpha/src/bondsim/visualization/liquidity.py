"""Liquidity calibration visualization data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def ranked_event_rates(events: pd.DataFrame, bond_col: str, sessions: int) -> pd.DataFrame:
    """Return sorted bond event rates."""

    rates = events.groupby(bond_col).size().sort_values() / max(int(sessions), 1)
    return pd.DataFrame({"rank": np.linspace(0.0, 1.0, len(rates)), "events_per_day": rates.to_numpy()})
