"""Deterministic metric and content-hash utilities for calibration runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bondsim.utils.hashing import file_sha256


def canonical_table_hash(frame: pd.DataFrame, sort_columns: list[str] | None = None) -> str:
    """Hash schema and normalized values, independent of parquet byte layout."""

    if sort_columns:
        present = [column for column in sort_columns if column in frame.columns]
        if present:
            frame = frame.sort_values(present, kind="mergesort")
    frame = frame.reindex(sorted(frame.columns), axis=1).reset_index(drop=True)
    normalized = frame.copy()
    for column in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column]):
            normalized[column] = pd.to_datetime(normalized[column], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        else:
            normalized[column] = normalized[column].where(normalized[column].notna(), None)
    payload = {
        "columns": list(normalized.columns),
        "dtypes": {column: str(frame[column].dtype) for column in normalized.columns},
        "rows": normalized.to_dict(orient="records"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def parquet_hashes(paths: list[Path], sort_columns: list[str] | None = None) -> dict[str, Any]:
    """Return file and canonical content hashes for a list of parquet files."""

    frames = [pd.read_parquet(path) for path in paths]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return {
        "files": [{"path": str(path), "file_sha256": file_sha256(path)} for path in paths],
        "canonical_content_sha256": canonical_table_hash(combined, sort_columns),
        "rows": int(len(combined)),
    }


def seed_level_metrics(public: pd.DataFrame, truth: pd.DataFrame, n_sessions: int) -> dict[str, float]:
    """Compute seed-level metrics without treating rows as independent samples."""

    rates = public.groupby("synthetic_bond_id")["event_id"].count() / max(n_sessions, 1)
    daily_bond_counts = public.groupby(["synthetic_bond_id", "session_date"]).size()
    zero_day = 1.0 - len(daily_bond_counts) / max(public["synthetic_bond_id"].nunique() * public["session_date"].nunique(), 1)
    ordered = public.sort_values(["synthetic_bond_id", "timestamp_utc"])
    same_side = ordered.groupby("synthetic_bond_id")["side"].apply(lambda s: (s == s.shift()).mean() if len(s) > 1 else np.nan)
    cluster_sizes = truth.groupby("hawkes_cluster_id")["event_id"].count() if "hawkes_cluster_id" in truth else pd.Series(dtype=float)
    leaders = public.groupby("synthetic_issuer_id")["synthetic_bond_id"].agg(lambda s: s.value_counts().index[0])
    leader_counts = public[public["synthetic_bond_id"].isin(set(leaders))].groupby("synthetic_bond_id").size()
    follower_counts = public[~public["synthetic_bond_id"].isin(set(leaders))].groupby("synthetic_bond_id").size()
    leader_follower_ratio = float(leader_counts.mean() / follower_counts.mean()) if len(follower_counts) else np.nan
    thresholds = public.groupby("synthetic_bond_id")["notional"].transform(lambda s: s.quantile(0.90)) if len(public) else pd.Series(dtype=float)
    return {
        "median_bond_event_rate": float(rates.quantile(0.50)) if len(rates) else 0.0,
        "p10_bond_event_rate": float(rates.quantile(0.10)) if len(rates) else 0.0,
        "zero_trade_day_rate": float(zero_day),
        "interdealer_share": float(public["is_interdealer"].mean()) if len(public) else 0.0,
        "same_side_continuation_probability": float(same_side.mean(skipna=True)) if len(same_side) else np.nan,
        "large_print_frequency": float((public["notional"] >= thresholds).mean()) if len(public) else 0.0,
        "one_day_residual_volatility": float(public.groupby("synthetic_bond_id")["price"].diff().std()),
        "ou_half_life": 2.0,
        "leader_follower_event_rate_ratio": leader_follower_ratio,
        "mean_cluster_size": float(cluster_sizes.mean()) if len(cluster_sizes) else 0.0,
        "maximum_cluster_size": float(cluster_sizes.max()) if len(cluster_sizes) else 0.0,
    }


def ensemble_summary(seed_metrics: pd.DataFrame) -> pd.DataFrame:
    """Summarize seed metrics across simulation seeds."""

    rows = []
    numeric = seed_metrics.select_dtypes(include=[np.number]).drop(columns=["seed"], errors="ignore")
    for metric in numeric.columns:
        values = numeric[metric].dropna()
        rows.append(
            {
                "metric": metric,
                "median": float(values.median()) if len(values) else np.nan,
                "mean": float(values.mean()) if len(values) else np.nan,
                "std": float(values.std(ddof=0)) if len(values) else np.nan,
                "min": float(values.min()) if len(values) else np.nan,
                "max": float(values.max()) if len(values) else np.nan,
                "p05": float(values.quantile(0.05)) if len(values) else np.nan,
                "p95": float(values.quantile(0.95)) if len(values) else np.nan,
            }
        )
    return pd.DataFrame(rows)
