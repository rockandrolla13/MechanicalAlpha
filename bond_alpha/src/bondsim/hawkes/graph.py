"""Sparse Hawkes graph parameters."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import eigs

from bondsim.config import BondSimConfig
from bondsim.scenarios import ScenarioFlags


@dataclass(frozen=True)
class HawkesGraph:
    same_side_mass: float
    opposite_side_mass: float
    leader_follower_mass: float
    half_lives_minutes: tuple[float, ...]
    spectral_radius: float


def build_hawkes_graph(universe: pd.DataFrame, config: BondSimConfig, flags: ScenarioFlags) -> HawkesGraph:
    if flags.sign_persistence:
        same = 0.20
        opposite = 0.05
    else:
        same = opposite = 0.10
    leader_follower = 0.03 if flags.leadlag else 0.0
    radius = estimate_spectral_radius(len(universe), same, opposite, leader_follower)
    max_radius = config.hawkes.maximum_spectral_radius
    if radius >= max_radius:
        scale = config.hawkes.controlled_target_spectral_radius / radius
        same *= scale
        opposite *= scale
        leader_follower *= scale
        radius = estimate_spectral_radius(len(universe), same, opposite, leader_follower)
    return HawkesGraph(
        same_side_mass=same,
        opposite_side_mass=opposite,
        leader_follower_mass=leader_follower,
        half_lives_minutes=tuple(config.hawkes.decay_half_lives_minutes),
        spectral_radius=float(radius),
    )


def estimate_spectral_radius(n_bonds: int, same: float, opposite: float, leader_follower: float) -> float:
    n = max(2, n_bonds * 2)
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    for bond in range(n_bonds):
        buy = 2 * bond
        sell = buy + 1
        rows.extend([buy, sell, buy, sell])
        cols.extend([buy, sell, sell, buy])
        data.extend([same, same, opposite, opposite])
    if leader_follower:
        for leader in range(0, n_bonds, 5):
            for follower in range(leader + 1, min(leader + 5, n_bonds)):
                rows.extend([2 * follower, 2 * follower + 1])
                cols.extend([2 * leader, 2 * leader + 1])
                data.extend([leader_follower, leader_follower])
    matrix = sparse.csr_matrix((data, (rows, cols)), shape=(n, n))
    if n <= 4:
        return float(max(abs(np.linalg.eigvals(matrix.toarray()))))
    return float(abs(eigs(matrix, k=1, return_eigenvectors=False)[0]))
