"""Probability calibration metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, log_loss


def probability_metrics(y_true: pd.Series, y_pred: pd.Series) -> dict[str, float]:
    mask = y_true.notna() & y_pred.notna()
    if not mask.any():
        return {"log_loss": float("nan"), "brier": float("nan")}
    y = y_true[mask].astype(int)
    p = np.clip(y_pred[mask].astype(float), 1e-6, 1 - 1e-6)
    return {"log_loss": float(log_loss(y, p)), "brier": float(brier_score_loss(y, p))}
