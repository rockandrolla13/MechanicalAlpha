"""Within-issuer leader-to-follower public alpha proxy."""

from __future__ import annotations

import pandas as pd


def compute(frame: pd.DataFrame) -> pd.Series:
    activity = frame.groupby(["scenario", "synthetic_issuer_id", "synthetic_bond_id"]).size()
    leaders = activity.groupby(level=[0, 1]).idxmax().map(lambda idx: idx[2]).to_dict()
    issuer_key = list(zip(frame["scenario"], frame["synthetic_issuer_id"], strict=False))
    leader_for_row = pd.Series([leaders.get(key) for key in issuer_key], index=frame.index)
    leader_events = frame["synthetic_bond_id"].eq(leader_for_row)
    signed_notional = frame["side"].astype(float) * frame["notional"].astype(float)
    leader_flow = signed_notional.where(leader_events, 0.0)
    pressure = leader_flow.groupby([frame["scenario"], frame["synthetic_issuer_id"]]).transform(lambda s: s.rolling(25, min_periods=1).sum())
    is_follower = ~leader_events
    return pd.Series(pressure.where(is_follower, 0.0), index=frame.index, name="leader_follower_pressure")
