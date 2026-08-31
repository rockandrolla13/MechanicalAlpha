"""Hierarchical empirical mark sampler."""

from __future__ import annotations

import numpy as np
import pandas as pd


class EmpiricalMarkSampler:
    """Samples production-observable event marks from training rows."""

    def __init__(self, events: pd.DataFrame):
        self.events = events.copy()
        self.global_rows = self.events.reset_index(drop=True)
        self.by_side = {
            int(side): group.reset_index(drop=True) for side, group in self.events.groupby("side", observed=True)
        }

    def sample(self, side: int, rng: np.random.Generator) -> dict[str, object]:
        pool = self.by_side.get(int(side), self.global_rows)
        row = pool.iloc[int(rng.integers(0, len(pool)))]
        delay = row.get("reporting_delay_ms", 0.0)
        delay = 0.0 if pd.isna(delay) else float(delay)
        venue = row.get("venue", "unknown")
        venue = "unknown" if pd.isna(venue) else str(venue)
        return {
            "notional": float(row.get("notional", 250000.0)),
            "is_interdealer": bool(row.get("is_interdealer", False)),
            "trade_type": str(row.get("trade_type", "unknown")),
            "venue_bucket": venue,
            "reporting_delay_ms": delay,
            "log_notional": float(row.get("log_notional", np.log1p(250000.0))),
        }
