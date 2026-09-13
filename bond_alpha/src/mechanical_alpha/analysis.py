"""Analysis helpers for notebook-facing alpha lab summaries."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


IDENTIFIER_COLUMNS = {
    "alpha_id",
    "bond_id",
    "issuer_id",
    "prediction_timestamp",
    "event_timestamp",
    "publication_timestamp",
    "revision_timestamp",
    "session_date",
}


def signal_columns(frame: pd.DataFrame) -> list[str]:
    """Return numeric signal-like columns, excluding identifiers."""

    if frame.empty:
        return []
    columns: list[str] = []
    for column in frame.columns:
        if column in IDENTIFIER_COLUMNS:
            continue
        if pd.api.types.is_numeric_dtype(frame[column]):
            columns.append(str(column))
    return sorted(columns)


def summarize_signals_by_alpha(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize a stacked standalone-alpha output frame by ``alpha_id``."""

    columns = [
        "alpha_id",
        "rows",
        "bonds",
        "signal_columns",
        "finite_signal_values",
        "mean_abs_signal",
        "first_prediction_timestamp",
        "last_prediction_timestamp",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if "alpha_id" not in frame.columns:
        raise ValueError("signal frame must include alpha_id")

    rows: list[dict[str, object]] = []
    for alpha_id, group in frame.groupby("alpha_id", sort=True, dropna=False):
        numeric_columns = signal_columns(group)
        numeric = group[numeric_columns] if numeric_columns else pd.DataFrame(index=group.index)
        finite_values = _finite_value_count(numeric)
        mean_abs = _mean_abs_value(numeric)
        timestamps = _timestamp_series(group)
        rows.append(
            {
                "alpha_id": str(alpha_id),
                "rows": int(len(group)),
                "bonds": int(group["bond_id"].nunique()) if "bond_id" in group.columns else 0,
                "signal_columns": int(len(numeric_columns)),
                "finite_signal_values": int(finite_values),
                "mean_abs_signal": mean_abs,
                "first_prediction_timestamp": timestamps.min() if not timestamps.empty else pd.NaT,
                "last_prediction_timestamp": timestamps.max() if not timestamps.empty else pd.NaT,
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values("alpha_id").reset_index(drop=True)


def summarize_signal_columns(frame: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Summarize selected signal columns across the full stacked output."""

    selected = list(columns) if columns is not None else signal_columns(frame)
    rows: list[dict[str, object]] = []
    for column in selected:
        values = pd.to_numeric(frame[column], errors="coerce") if column in frame.columns else pd.Series(dtype=float)
        finite = values[np.isfinite(values)]
        rows.append(
            {
                "column": column,
                "finite_count": int(len(finite)),
                "mean": float(finite.mean()) if len(finite) else np.nan,
                "std": float(finite.std(ddof=0)) if len(finite) else np.nan,
                "min": float(finite.min()) if len(finite) else np.nan,
                "max": float(finite.max()) if len(finite) else np.nan,
            }
        )
    return pd.DataFrame(rows, columns=["column", "finite_count", "mean", "std", "min", "max"])


def portfolio_pnl_hooks(signals: pd.DataFrame, summary: pd.DataFrame) -> dict[str, object]:
    """Return explicit handoff metadata for future portfolio and PnL modules."""

    return {
        "signals_rows": int(len(signals)),
        "summary_rows": int(len(summary)),
        "required_next_modules": ("portfolio", "pnl_metrics"),
        "status": "not_invoked",
    }


def _timestamp_series(frame: pd.DataFrame) -> pd.Series:
    if "prediction_timestamp" not in frame.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(frame["prediction_timestamp"], errors="coerce").dropna()


def _finite_value_count(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    values = frame.to_numpy(dtype=float, copy=False)
    return int(np.isfinite(values).sum())


def _mean_abs_value(frame: pd.DataFrame) -> float:
    if frame.empty:
        return np.nan
    values = frame.to_numpy(dtype=float, copy=False)
    finite = values[np.isfinite(values)]
    return float(np.mean(np.abs(finite))) if finite.size else np.nan
