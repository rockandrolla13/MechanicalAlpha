"""Short-horizon same-side flow persistence features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bondalpha.features.common import EPSILON


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    side = frame["side"].astype(float)
    group = frame.groupby(["scenario", "synthetic_bond_id"], sort=False)
    count_buy = group["side"].transform(lambda s: s.eq(1).rolling(20, min_periods=1).sum())
    count_sell = group["side"].transform(lambda s: s.eq(-1).rolling(20, min_periods=1).sum())
    imbalance = (count_buy - count_sell) / (count_buy + count_sell + EPSILON)
    last_side = group["side"].shift(1).fillna(0).astype(float)
    run = _same_side_run(frame)
    return pd.DataFrame(
        {
            "flow_persistence": last_side * imbalance,
            "last_side": last_side,
            "same_side_run_length": run,
            "log_intensity_ratio": np.log((count_buy + EPSILON) / (count_sell + EPSILON)),
        },
        index=frame.index,
    )


def _same_side_run(frame: pd.DataFrame) -> pd.Series:
    values = []
    for _, group in frame.groupby(["scenario", "synthetic_bond_id"], sort=False):
        previous = None
        run = 0
        for side in group["side"]:
            run = run + 1 if side == previous else 1
            values.append(run)
            previous = side
    return pd.Series(values, index=frame.index, dtype=float)
