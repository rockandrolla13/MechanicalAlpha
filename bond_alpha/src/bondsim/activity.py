"""Session calendar and activity profiles."""

from __future__ import annotations

import numpy as np
import pandas as pd


def session_calendar(start: str, n_sessions: int) -> list[pd.Timestamp]:
    return list(pd.bdate_range(start=start, periods=n_sessions))


def intraday_bucket_probabilities(n_buckets: int) -> np.ndarray:
    x = np.linspace(-1.0, 1.0, n_buckets)
    weights = 0.65 + 0.70 * (x**2)
    return weights / weights.sum()


def daily_activity_multipliers(n_sessions: int, rng: np.random.Generator) -> np.ndarray:
    shocks = rng.normal(0.0, 0.20, size=n_sessions)
    state = np.zeros(n_sessions)
    for idx in range(1, n_sessions):
        state[idx] = 0.75 * state[idx - 1] + shocks[idx]
    values = np.exp(state)
    return values / values.mean()
