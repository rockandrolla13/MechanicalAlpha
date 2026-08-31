"""Alpha Factory public feature construction."""

from __future__ import annotations

import pandas as pd

from bondalpha.features import controls, flow_persistence, leader_follower, relative_value, reversal
from bondalpha.features.common import ordered


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    data = ordered(frame)
    pieces = [
        reversal.compute(data),
        flow_persistence.compute(data),
        leader_follower.compute(data),
        relative_value.compute(data),
        controls.compute(data),
    ]
    features = pd.concat(pieces, axis=1)
    features.insert(0, "event_id", data["event_id"].to_numpy())
    features.insert(1, "scenario", data["scenario"].to_numpy())
    features.insert(2, "timestamp_utc", data["timestamp_utc"].to_numpy())
    features.insert(3, "synthetic_bond_id", data["synthetic_bond_id"].to_numpy())
    return features
