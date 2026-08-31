"""Reproducibility visualization data."""

from __future__ import annotations

import pandas as pd


def hash_comparison_table(left: str, right: str) -> pd.DataFrame:
    """Return a one-row hash comparison table."""

    return pd.DataFrame([{"left_hash": left, "right_hash": right, "matches": left == right}])
