"""Simple issuer-relative public price dislocation feature."""

from __future__ import annotations

import pandas as pd

from bondalpha.features.common import robust_zscore


def compute(frame: pd.DataFrame) -> pd.Series:
    bond_return = frame.groupby(["scenario", "synthetic_bond_id"])["price"].diff().fillna(0.0)
    issuer_return = bond_return.groupby([frame["scenario"], frame["synthetic_issuer_id"]]).transform("mean")
    gap = bond_return - issuer_return
    return gap.groupby(frame["scenario"]).transform(robust_zscore).rename("relative_value_gap")
