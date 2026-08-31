"""Public-data labels used by Alpha Factory."""

from __future__ import annotations

import pandas as pd


def add_public_labels(frame: pd.DataFrame, horizons: list[str]) -> pd.DataFrame:
    """Add future price-change labels from public transaction prices only."""

    out = frame.sort_values(["scenario", "synthetic_bond_id", "timestamp_utc", "event_id"]).copy()
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"])
    grouped = out.groupby(["scenario", "synthetic_bond_id"], sort=False)
    for horizon in horizons:
        steps = _horizon_steps(horizon)
        future_price = grouped["price"].shift(-steps)
        out[f"future_price_change_{horizon}"] = future_price - out["price"]
        out[f"future_price_up_{horizon}"] = (out[f"future_price_change_{horizon}"] > 0).astype("float")
        out.loc[future_price.isna(), f"future_price_up_{horizon}"] = pd.NA
    return out


def _horizon_steps(horizon: str) -> int:
    return {"30m": 1, "2h": 3, "1d": 8, "5d": 40}.get(horizon, 1)
