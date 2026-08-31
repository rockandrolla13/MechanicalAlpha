"""Deterministic trading-session calendar helpers for BondSim."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class SessionCalendar:
    """Trading sessions with fixed open and close times."""

    sessions: pd.DatetimeIndex
    session_open: time = time(9, 30)
    session_close: time = time(16, 0)
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        normalized = pd.DatetimeIndex(pd.to_datetime(self.sessions).normalize()).sort_values().unique()
        object.__setattr__(self, "sessions", normalized)

    def contains(self, timestamp: pd.Timestamp) -> bool:
        ts = _as_timestamp(timestamp, self.timezone)
        return ts.normalize() in self.sessions

    def bounds_for(self, session: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
        day = _as_timestamp(session, self.timezone).normalize()
        if day not in self.sessions:
            raise ValueError(f"session is not in calendar: {day.date()}")
        open_ts = pd.Timestamp.combine(day.date(), self.session_open).tz_localize(self.timezone)
        close_ts = pd.Timestamp.combine(day.date(), self.session_close).tz_localize(self.timezone)
        return open_ts, close_ts

    def session_for(self, timestamp: pd.Timestamp) -> pd.Timestamp:
        ts = _as_timestamp(timestamp, self.timezone)
        day = ts.normalize()
        if day not in self.sessions:
            raise ValueError(f"timestamp is outside configured sessions: {timestamp}")
        open_ts, close_ts = self.bounds_for(day)
        if not (open_ts <= ts <= close_ts):
            raise ValueError(f"timestamp is outside session hours: {timestamp}")
        return day


def build_session_calendar(
    start: str | pd.Timestamp,
    n_sessions: int,
    holidays: Iterable[str | pd.Timestamp] | None = None,
    timezone: str = "UTC",
    session_open: str | time = "09:30",
    session_close: str | time = "16:00",
) -> SessionCalendar:
    """Build a weekday calendar excluding explicit holidays."""

    if n_sessions <= 0:
        raise ValueError("n_sessions must be positive")
    holiday_days = {
        _as_timestamp(day, timezone).normalize().tz_localize(None)
        for day in (holidays or [])
    }
    start_day = _as_timestamp(start, timezone).normalize().tz_localize(None)
    days: list[pd.Timestamp] = []
    cursor = start_day
    while len(days) < n_sessions:
        if cursor.weekday() < 5 and cursor not in holiday_days:
            days.append(cursor)
        cursor += pd.Timedelta(days=1)
    return SessionCalendar(
        sessions=pd.DatetimeIndex(days),
        session_open=_parse_time(session_open),
        session_close=_parse_time(session_close),
        timezone=timezone,
    )


def assign_session_dates(
    frame: pd.DataFrame,
    timestamp_col: str = "timestamp_utc",
    timezone: str = "UTC",
) -> pd.DataFrame:
    """Return a copy with normalized session_date, year, and month columns."""

    result = frame.copy()
    timestamps = pd.to_datetime(result[timestamp_col], utc=True)
    if timezone != "UTC":
        timestamps = timestamps.dt.tz_convert(timezone)
    result["session_date"] = timestamps.dt.date.astype(str)
    result["year"] = timestamps.dt.year.astype("int16")
    result["month"] = timestamps.dt.month.astype("int8")
    return result


def assert_no_weekend_sessions(sessions: Iterable[str | pd.Timestamp]) -> None:
    """Raise when any configured session falls on Saturday or Sunday."""

    bad = [str(pd.Timestamp(day).date()) for day in sessions if pd.Timestamp(day).weekday() >= 5]
    if bad:
        raise ValueError(f"weekend sessions are not allowed: {bad}")


def _as_timestamp(value: str | pd.Timestamp, timezone: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize(timezone)
    return ts.tz_convert(timezone)


def _parse_time(value: str | time) -> time:
    if isinstance(value, time):
        return value
    parsed = pd.Timestamp(value)
    return time(parsed.hour, parsed.minute, parsed.second)
