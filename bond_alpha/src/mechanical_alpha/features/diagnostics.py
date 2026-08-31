"""Diagnostics for deterministic feature frames."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FeatureDiagnostic:
    """Simple diagnostic summary for one feature column."""

    feature: str
    non_null_rate: float
    zero_rate: float
    unique_values: int
    is_constant: bool
    is_sparse: bool
    has_extreme_values: bool


def diagnose_feature_frame(
    features: pd.DataFrame,
    bonds: pd.DataFrame | None = None,
    *,
    sparse_threshold: float = 0.05,
    extreme_abs_threshold: float = 1.0e6,
) -> pd.DataFrame:
    """Return coverage and stability diagnostics for feature columns.

    Identifier columns are ignored.
    When bond metadata are supplied, group coverage is reported by available
    rating, sector, duration, liquidity bucket, and issuer fields.
    """

    ignore = {"prediction_timestamp", "bond_id", "issuer_id"}
    feature_columns = [column for column in features.columns if column not in ignore]
    rows = [
        _diagnose_one(features[column], column, sparse_threshold, extreme_abs_threshold).__dict__
        for column in feature_columns
    ]
    output = pd.DataFrame(rows)
    if bonds is not None and not bonds.empty and feature_columns:
        grouped = _group_coverage(features, bonds, feature_columns)
        output.attrs["group_coverage"] = grouped
    return output


def _diagnose_one(
    values: pd.Series,
    name: str,
    sparse_threshold: float,
    extreme_abs_threshold: float,
) -> FeatureDiagnostic:
    non_null = values.notna()
    numeric = pd.to_numeric(values, errors="coerce")
    non_null_rate = float(non_null.mean()) if len(values) else 0.0
    zero_rate = float((numeric.fillna(np.nan) == 0).mean()) if len(values) else 0.0
    unique_values = int(values.dropna().nunique())
    return FeatureDiagnostic(
        feature=name,
        non_null_rate=non_null_rate,
        zero_rate=zero_rate,
        unique_values=unique_values,
        is_constant=unique_values <= 1 and non_null_rate > 0.0,
        is_sparse=non_null_rate < sparse_threshold,
        has_extreme_values=bool((numeric.abs() > extreme_abs_threshold).any()),
    )


def _group_coverage(features: pd.DataFrame, bonds: pd.DataFrame, feature_columns: list[str]) -> dict[str, pd.DataFrame]:
    join_cols = [column for column in ("bond_id", "issuer_id") if column in features.columns and column in bonds.columns]
    if not join_cols:
        return {}
    merged = features.merge(bonds, on=join_cols, how="left", suffixes=("", "_bond"))
    group_fields = [
        column
        for column in ("rating", "sector", "duration", "liquidity_bucket", "issuer_id", "venue")
        if column in merged.columns
    ]
    coverage: dict[str, pd.DataFrame] = {}
    for group_field in group_fields:
        rows = []
        for value, group in merged.groupby(group_field, dropna=False):
            row = {"group_field": group_field, "group_value": value, "rows": len(group)}
            for feature in feature_columns:
                row[f"{feature}_non_null_rate"] = float(group[feature].notna().mean())
            rows.append(row)
        coverage[group_field] = pd.DataFrame(rows)
    return coverage
