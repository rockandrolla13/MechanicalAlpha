"""Large-print reversal alpha proxy from public trade fields."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bondalpha.features.common import EPSILON


def compute(frame: pd.DataFrame) -> pd.Series:
    notional = frame["notional"].astype(float)
    median_by_bond = frame.groupby(["scenario", "synthetic_bond_id"])["notional"].transform("median").clip(lower=EPSILON)
    p90_by_bond = frame.groupby(["scenario", "synthetic_bond_id"])["notional"].transform(lambda s: s.quantile(0.90))
    large = notional >= p90_by_bond
    size = np.sqrt(notional / median_by_bond).clip(upper=5.0)
    return pd.Series(-frame["side"].astype(float) * size * large.astype(float), index=frame.index, name="reversal_pressure")
