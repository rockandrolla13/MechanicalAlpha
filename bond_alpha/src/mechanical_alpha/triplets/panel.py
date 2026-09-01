"""Triplet-panel construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.triplets.clocks import ClockIndex


def sample_state_on_clock(
    state: pd.DataFrame,
    clock: ClockIndex,
    *,
    time_col: str = "timestamp",
    instrument_col: str = "bond_id",
    value_col: str = "price",
) -> pd.DataFrame:
    """Sample an instrument state with backward as-of joins at each clock time."""

    columns = ["clock", "clock_index", "timestamp", instrument_col, value_col]
    if state.empty or len(clock.timestamps) == 0:
        return pd.DataFrame(columns=columns)

    clean = state[[time_col, instrument_col, value_col]].copy()
    clean[time_col] = pd.to_datetime(clean[time_col], utc=False)
    clean = clean.sort_values([instrument_col, time_col], kind="mergesort")
    samples: list[pd.DataFrame] = []
    clock_frame = clock.frame().rename(columns={"timestamp": time_col})
    for instrument, group in clean.groupby(instrument_col, sort=False):
        left = clock_frame.copy()
        right = group.sort_values(time_col, kind="mergesort")
        merged = pd.merge_asof(left.sort_values(time_col), right, on=time_col, direction="backward", allow_exact_matches=True)
        merged[instrument_col] = instrument
        samples.append(merged.rename(columns={time_col: "timestamp"})[columns])
    return pd.concat(samples, ignore_index=True).sort_values([instrument_col, "timestamp"], kind="mergesort").reset_index(drop=True)


def build_triplet_panel(
    sampled: pd.DataFrame,
    *,
    lags: tuple[int, ...],
    horizons: tuple[int, ...],
    anchors: tuple[int, ...] = (0,),
    value_col: str = "price",
    instrument_col: str = "bond_id",
    target_type: str = "clean_price",
    duration_col: str | None = None,
) -> pd.DataFrame:
    """Build lag-anchor-horizon rows for triplet estimation."""

    rows: list[dict[str, object]] = []
    if sampled.empty:
        return pd.DataFrame()
    ordered = sampled.sort_values([instrument_col, "clock_index"], kind="mergesort")
    for instrument, group in ordered.groupby(instrument_col, sort=False):
        group = group.reset_index(drop=True)
        values = pd.to_numeric(group[value_col], errors="coerce").to_numpy(dtype=float)
        durations = None
        if duration_col and duration_col in group.columns:
            durations = pd.to_numeric(group[duration_col], errors="coerce").to_numpy(dtype=float)
        for idx in range(len(group)):
            for anchor in anchors:
                anchor_idx = idx + int(anchor)
                if anchor_idx < 0 or anchor_idx >= len(group):
                    continue
                for lag in lags:
                    lag_idx = anchor_idx - int(lag)
                    if lag_idx < 0:
                        continue
                    past_move = values[anchor_idx] - values[lag_idx]
                    if target_type == "spread_implied":
                        duration = 1.0 if durations is None or not np.isfinite(durations[anchor_idx]) else durations[anchor_idx]
                        past_move = -duration * past_move
                    for horizon in horizons:
                        future_idx = anchor_idx + int(horizon)
                        if future_idx >= len(group):
                            continue
                        future_move = values[future_idx] - values[anchor_idx]
                        if target_type == "spread_implied":
                            duration = 1.0 if durations is None or not np.isfinite(durations[anchor_idx]) else durations[anchor_idx]
                            future_move = -duration * future_move
                        if not np.isfinite(past_move) or not np.isfinite(future_move):
                            continue
                        rows.append(
                            {
                                instrument_col: instrument,
                                "clock_index": int(group.loc[anchor_idx, "clock_index"]),
                                "timestamp": group.loc[anchor_idx, "timestamp"],
                                "lag": int(lag),
                                "anchor": int(anchor),
                                "horizon": int(horizon),
                                "target_type": target_type,
                                "past_move": float(past_move),
                                "future_move": float(future_move),
                            }
                        )
    return pd.DataFrame(rows)

