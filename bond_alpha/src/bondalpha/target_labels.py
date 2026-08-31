"""Separate public-data target construction for Alpha Factory research."""

from __future__ import annotations

import pandas as pd


def build_target_labels(frame: pd.DataFrame, horizons: list[str] | tuple[str, ...]) -> pd.DataFrame:
    """Build public observable labels without reading truth columns."""

    out = frame.sort_values(["scenario", "synthetic_bond_id", "timestamp_utc", "event_id"]).copy()
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True)
    grouped = out.groupby(["scenario", "synthetic_bond_id"], sort=False)
    issuer_grouped = out.groupby(["scenario", "synthetic_issuer_id"], sort=False)
    for horizon in horizons:
        steps = _horizon_steps(horizon)
        future_price = grouped["price"].shift(-steps)
        out[f"future_clean_price_move_{horizon}"] = future_price - out["price"]
        issuer_future = issuer_grouped["price"].shift(-steps)
        issuer_move = issuer_future - out["price"]
        out[f"future_issuer_residual_move_{horizon}"] = out[f"future_clean_price_move_{horizon}"] - issuer_move
        future_flow = grouped["side"].shift(-steps) * grouped["notional"].shift(-steps)
        out[f"future_signed_flow_{horizon}"] = future_flow
    out["next_event_side"] = grouped["side"].shift(-1)
    return out


def _horizon_steps(horizon: str) -> int:
    return {"30m": 1, "2h": 3, "1d": 8, "5d": 40}.get(str(horizon), 1)
