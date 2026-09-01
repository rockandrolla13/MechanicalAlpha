"""Adapted clocks for triplet research.

Calendar clocks move in physical time.
Event clocks move after observable event counts.
Information clocks move after nonnegative observable activity accumulates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class ClockIndex:
    """A deterministic sequence of decision times."""

    name: str
    timestamps: pd.DatetimeIndex
    diagnostics: dict[str, object]

    def frame(self) -> pd.DataFrame:
        """Return the clock as a tabular index."""

        return pd.DataFrame({"clock": self.name, "clock_index": range(len(self.timestamps)), "timestamp": self.timestamps})


def build_calendar_clock(start: object, end: object, frequency: str, *, name: str = "calendar") -> ClockIndex:
    """Build a fixed physical-time clock."""

    timestamps = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=frequency)
    return ClockIndex(name=name, timestamps=pd.DatetimeIndex(timestamps), diagnostics={"frequency": frequency, "count": len(timestamps)})


def build_event_clock(events: pd.DataFrame, threshold: int, *, timestamp_col: str = "timestamp", name: str = "event") -> ClockIndex:
    """Build a clock that ticks every `threshold` observable events."""

    if threshold <= 0:
        raise ValueError("threshold must be positive")
    if events.empty:
        return ClockIndex(name=name, timestamps=pd.DatetimeIndex([]), diagnostics={"threshold": threshold, "count": 0})
    ordered = pd.to_datetime(events[timestamp_col], utc=False).sort_values(kind="mergesort").reset_index(drop=True)
    ticks = ordered.iloc[threshold - 1 :: threshold]
    return ClockIndex(name=name, timestamps=pd.DatetimeIndex(ticks), diagnostics={"threshold": threshold, "count": len(ticks)})


def build_information_clock(
    events: pd.DataFrame,
    threshold: float,
    *,
    activity: str | Callable[[pd.DataFrame], pd.Series] = "notional",
    timestamp_col: str = "timestamp",
    name: str = "information",
) -> ClockIndex:
    """Build a clock that ticks after cumulative nonnegative activity crosses a threshold."""

    if threshold <= 0:
        raise ValueError("threshold must be positive")
    if events.empty:
        return ClockIndex(name=name, timestamps=pd.DatetimeIndex([]), diagnostics={"threshold": threshold, "count": 0})

    ordered = events.sort_values(timestamp_col, kind="mergesort").reset_index(drop=True)
    scores = activity(ordered) if callable(activity) else pd.to_numeric(ordered[activity], errors="coerce")
    scores = pd.Series(scores, index=ordered.index).fillna(0.0).astype(float)
    if (scores < 0).any():
        raise ValueError("information-clock activity must be nonnegative and adapted")

    ticks: list[pd.Timestamp] = []
    accumulator = 0.0
    for ts, value in zip(pd.to_datetime(ordered[timestamp_col], utc=False), scores, strict=True):
        accumulator += float(value)
        if accumulator >= threshold:
            ticks.append(pd.Timestamp(ts))
            accumulator = 0.0
    return ClockIndex(name=name, timestamps=pd.DatetimeIndex(ticks), diagnostics={"threshold": threshold, "count": len(ticks)})

