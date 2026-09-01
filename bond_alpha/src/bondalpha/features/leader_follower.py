"""Within-issuer leader-to-follower public alpha proxy.

The signal is point-in-time.
For each event row, the issuer leader is selected from prior observed activity
only. The follower pressure uses only prior leader trades for the same scenario
and issuer.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute(
    frame: pd.DataFrame,
    *,
    window_events: int = 25,
    half_life_events: float = 10.0,
    min_prior_leader_events: int = 1,
) -> pd.Series:
    """Compute prior leader-flow pressure for non-leader issuer siblings.

    The result is positive when prior leader customer-buy flow is positive.
    Leader rows receive zero because the effect is defined leader-to-follower.
    """

    if window_events <= 0:
        raise ValueError("window_events must be positive")
    if half_life_events <= 0:
        raise ValueError("half_life_events must be positive")

    required = {"scenario", "synthetic_issuer_id", "synthetic_bond_id", "timestamp_utc", "event_id", "side", "notional"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"leader_follower requires columns: {missing}")

    ordered = frame.copy()
    ordered["timestamp_utc"] = pd.to_datetime(ordered["timestamp_utc"], utc=True)
    ordered["original_index"] = ordered.index
    ordered = ordered.sort_values(["scenario", "synthetic_issuer_id", "timestamp_utc", "event_id"], kind="mergesort")

    out = pd.Series(0.0, index=frame.index, name="leader_follower_pressure")
    for _, group in ordered.groupby(["scenario", "synthetic_issuer_id"], sort=False):
        values = _compute_one_issuer(
            group,
            window_events=window_events,
            half_life_events=half_life_events,
            min_prior_leader_events=min_prior_leader_events,
        )
        out.loc[values.index] = values
    return out


def _compute_one_issuer(
    group: pd.DataFrame,
    *,
    window_events: int,
    half_life_events: float,
    min_prior_leader_events: int,
) -> pd.Series:
    counts: dict[str, int] = {}
    signed_history: dict[str, list[float]] = {}
    outputs: dict[int, float] = {}
    decay_base = math.log(2.0) / float(half_life_events)

    for row in group.itertuples(index=False):
        bond_id = str(row.synthetic_bond_id)
        original_index = int(row.original_index)
        leader_id = _prior_leader(counts)
        if leader_id is None or leader_id == bond_id or counts.get(leader_id, 0) < min_prior_leader_events:
            outputs[original_index] = 0.0
        else:
            history = signed_history.get(leader_id, [])
            outputs[original_index] = _decayed_normalized_pressure(history, decay_base, window_events)

        signed = _signed_size(row.side, row.notional)
        counts[bond_id] = counts.get(bond_id, 0) + 1
        signed_history.setdefault(bond_id, []).append(signed)

    return pd.Series(outputs, dtype=float, name="leader_follower_pressure")


def _prior_leader(counts: dict[str, int]) -> str | None:
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _signed_size(side: object, notional: object) -> float:
    side_value = float(side)
    notional_value = max(float(notional), 0.0)
    if side_value not in {-1.0, 1.0} or not np.isfinite(notional_value):
        return 0.0
    return side_value * math.sqrt(notional_value)


def _decayed_normalized_pressure(history: list[float], decay_base: float, window_events: int) -> float:
    tail = history[-window_events:]
    if not tail:
        return 0.0
    ages = np.arange(len(tail) - 1, -1, -1, dtype=float)
    weights = np.exp(-decay_base * ages)
    values = np.asarray(tail, dtype=float)
    scale = float(np.nanmedian(np.abs(values)))
    if not np.isfinite(scale) or scale <= 0:
        return 0.0
    return float(np.sum(weights * values) / (scale * np.sum(weights)))
