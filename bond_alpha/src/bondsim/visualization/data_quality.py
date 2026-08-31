"""Data-quality visualization entry points."""

from __future__ import annotations

import pandas as pd


def missingness_table(frame: pd.DataFrame) -> pd.DataFrame:
    """Return field-level missingness for deterministic plot data."""

    return frame.isna().mean().rename_axis("field").reset_index(name="missing_rate")
