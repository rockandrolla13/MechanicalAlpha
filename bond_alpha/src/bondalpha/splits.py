"""Time-ordered split helpers."""

from __future__ import annotations

import pandas as pd


def assign_time_splits(frame: pd.DataFrame, train_fraction: float, validation_fraction: float) -> pd.Series:
    dates = sorted(pd.Series(frame["session_date"]).astype(str).unique())
    if not dates:
        return pd.Series([], dtype="object")
    train_end = max(1, int(len(dates) * train_fraction))
    validation_end = max(train_end + 1, int(len(dates) * (train_fraction + validation_fraction)))
    date_to_split = {}
    for idx, date in enumerate(dates):
        if idx < train_end:
            date_to_split[date] = "train"
        elif idx < validation_end:
            date_to_split[date] = "validation"
        else:
            date_to_split[date] = "test"
    return pd.Series(frame["session_date"]).astype(str).map(date_to_split)
