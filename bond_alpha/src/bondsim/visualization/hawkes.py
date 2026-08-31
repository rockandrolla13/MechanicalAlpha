"""Hawkes calibration visualization data."""

from __future__ import annotations

import pandas as pd


def branching_mass_table(same_side: float, opposite_side: float, leader_follower: float) -> pd.DataFrame:
    """Return pooled branching masses by edge class."""

    return pd.DataFrame(
        [
            {"edge_class": "same_bond_same_side", "mass": float(same_side)},
            {"edge_class": "same_bond_opposite_side", "mass": float(opposite_side)},
            {"edge_class": "issuer_leader_to_follower", "mass": float(leader_follower)},
        ]
    )
