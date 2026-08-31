"""Business-calendar helpers for point-in-time alpha labels."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class BusinessCalendar:
    """Deterministic weekday calendar with an explicit holiday set."""

    holidays: frozenset[pd.Timestamp] = field(default_factory=frozenset)

    @classmethod
    def from_dates(cls, holidays: list[str | date | pd.Timestamp] | None = None) -> "BusinessCalendar":
        values = frozenset(pd.Timestamp(day).normalize() for day in (holidays or []))
        return cls(holidays=values)

    def is_business_day(self, value: str | date | pd.Timestamp) -> bool:
        day = pd.Timestamp(value).normalize()
        return day.weekday() < 5 and day not in self.holidays

    def add_business_days(self, timestamp: pd.Timestamp, days: int) -> pd.Timestamp:
        """Add business days while preserving the intraday time."""

        if days < 0:
            raise ValueError("days must be nonnegative")
        ts = pd.Timestamp(timestamp)
        out = ts
        remaining = days
        while remaining:
            out = out + pd.Timedelta(days=1)
            if self.is_business_day(out):
                remaining -= 1
        return out

    def add_horizon(self, timestamp: pd.Timestamp, horizon: str) -> pd.Timestamp:
        """Add a supported point-in-time label horizon."""

        ts = pd.Timestamp(timestamp)
        normalized = horizon.strip().lower().replace(" ", "")
        if normalized in {"30m", "30min", "30mins", "30minutes"}:
            return ts + pd.Timedelta(minutes=30)
        if normalized in {"2h", "2hr", "2hrs", "2hour", "2hours"}:
            return ts + pd.Timedelta(hours=2)
        if normalized in {"1bd", "1bday", "1businessday"}:
            return self.add_business_days(ts, 1)
        if normalized in {"5bd", "5bday", "5businessdays"}:
            return self.add_business_days(ts, 5)
        raise ValueError(f"unsupported horizon: {horizon}")


DEFAULT_HORIZONS: tuple[str, ...] = ("30m", "2h", "1bd", "5bd")

