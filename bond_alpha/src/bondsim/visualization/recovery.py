"""Positive-control visualization data."""

from __future__ import annotations

import pandas as pd


def planted_state_summary(truth: pd.DataFrame) -> pd.DataFrame:
    """Return controlled effect state magnitudes."""

    columns = ["planted_large_print_state", "planted_leadlag_state"]
    return truth[columns].abs().mean().rename_axis("component").reset_index(name="mean_absolute_state")
