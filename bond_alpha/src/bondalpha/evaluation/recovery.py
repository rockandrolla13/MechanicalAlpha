"""Observable recovery summaries that do not require truth data."""

from __future__ import annotations

import pandas as pd


def public_recovery_summary(frame: pd.DataFrame) -> dict[str, float]:
    return {
        "mean_reversal_pressure": float(frame.get("reversal_pressure", pd.Series(dtype=float)).mean()),
        "mean_flow_persistence": float(frame.get("flow_persistence", pd.Series(dtype=float)).mean()),
        "mean_leader_follower_pressure": float(frame.get("leader_follower_pressure", pd.Series(dtype=float)).mean()),
    }
