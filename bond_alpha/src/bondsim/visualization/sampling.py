"""Deterministic sampling helpers for plots."""

from __future__ import annotations

import hashlib

import pandas as pd


def stable_event_sample(frame: pd.DataFrame, max_rows: int, key: str = "event_id") -> pd.DataFrame:
    """Return a deterministic sample based on a stable hash of event_id."""

    if len(frame) <= max_rows:
        return frame.copy()
    hashes = frame[key].astype(str).map(lambda value: int(hashlib.sha256(value.encode()).hexdigest()[:16], 16))
    return frame.assign(_sample_hash=hashes).sort_values("_sample_hash").head(max_rows).drop(columns="_sample_hash")
