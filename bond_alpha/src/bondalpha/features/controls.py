"""Control features that should not carry planted truth by construction."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute(frame: pd.DataFrame) -> pd.DataFrame:
    notional = np.log1p(frame["notional"].astype(float))
    liquidity = frame.groupby(["scenario", "synthetic_bond_id"])["event_id"].transform("count").astype(float)
    return pd.DataFrame(
        {
            "liquidity_control": np.log1p(liquidity),
            "log_notional_control": notional,
            "interdealer_control": frame["is_interdealer"].astype(float),
        },
        index=frame.index,
    )
