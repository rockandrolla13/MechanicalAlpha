"""Price-model visualization data."""

from __future__ import annotations

import pandas as pd


def price_change_table(events: pd.DataFrame) -> pd.DataFrame:
    """Return one-event price changes by synthetic bond."""

    changes = events.sort_values(["synthetic_bond_id", "timestamp_utc"]).groupby("synthetic_bond_id")["price"].diff()
    return changes.dropna().rename("price_change").reset_index(drop=True).to_frame()
