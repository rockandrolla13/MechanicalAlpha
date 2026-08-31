"""Activity profile visualization data."""

from __future__ import annotations

import pandas as pd


def intraday_share(events: pd.DataFrame, timestamp_col: str = "timestamp_utc") -> pd.DataFrame:
    """Return hourly event shares."""

    buckets = pd.to_datetime(events[timestamp_col], utc=True).dt.hour
    return buckets.value_counts(normalize=True).sort_index().rename_axis("hour").reset_index(name="share")
