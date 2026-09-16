"""Small deterministic sklearn models for the frozen alpha spec."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


@dataclass(frozen=True)
class FittedAlphaModel:
    feature_columns: list[str]
    target_column: str
    model: object


def fit_logistic(features: pd.DataFrame, labels: pd.DataFrame, target_column: str) -> FittedAlphaModel:
    merged = features.merge(labels[["event_id", target_column, "split"]], on="event_id", how="inner")
    train = merged[merged["split"].eq("train") & merged[target_column].notna()].copy()
    feature_columns = [c for c in features.columns if c not in {"event_id", "scenario", "timestamp_utc", "synthetic_bond_id"}]
    x = train[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    y = train[target_column].astype(int)
    if y.nunique() < 2:
        raise RuntimeError(f"target {target_column} has fewer than two classes")
    model = make_pipeline(StandardScaler(), LogisticRegression(random_state=0, max_iter=500))
    model.fit(x, y)
    return FittedAlphaModel(feature_columns=feature_columns, target_column=target_column, model=model)


def predict_proba(fitted: FittedAlphaModel, features: pd.DataFrame) -> pd.Series:
    x = features[fitted.feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    values = fitted.model.predict_proba(x)[:, 1]
    return pd.Series(values, index=features.index, name="prediction")
