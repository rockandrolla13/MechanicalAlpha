"""Synthetic universe construction."""

from __future__ import annotations

import numpy as np
import pandas as pd

from bondsim.config import BondSimConfig
from bondsim.liquidity import target_rates_from_ranks


def build_universe(real_bonds: pd.DataFrame, config: BondSimConfig, rng: np.random.Generator, mode: str) -> pd.DataFrame:
    if mode == "smoke":
        n_bonds = config.simulation.smoke_bonds
    elif mode == "medium":
        n_bonds = config.simulation.medium_bonds
    else:
        n_bonds = config.universe.n_bonds
    if real_bonds.empty:
        real_bonds = _fallback_real_bonds(n_bonds)
    sampled = real_bonds.sample(n=n_bonds, replace=len(real_bonds) < n_bonds, random_state=int(rng.integers(0, 2**31 - 1)))
    sampled = sampled.reset_index(drop=True).copy()
    issuer_count = min(config.universe.target_issuers, max(1, int(np.ceil(n_bonds / 5))))
    if mode == "smoke":
        issuer_count = max(3, min(max(issuer_count, 3), int(np.ceil(n_bonds / 3))))
    elif mode == "medium":
        issuer_count = max(20, min(issuer_count, int(np.ceil(n_bonds / 5))))
    sampled["synthetic_bond_id"] = [f"SB{i:05d}" for i in range(n_bonds)]
    sampled["synthetic_issuer_id"] = [f"SI{i % issuer_count:04d}" for i in range(n_bonds)]
    sampled["target_events_per_day"] = target_rates_from_ranks(sampled, config.liquidity).to_numpy()
    sampled["issuer_rank"] = sampled.groupby("synthetic_issuer_id")["target_events_per_day"].rank(ascending=False, method="first")
    sampled["is_issuer_leader"] = sampled["issuer_rank"].eq(1)
    sampled["is_leadlag_follower"] = sampled.groupby("synthetic_issuer_id")["target_events_per_day"].rank(
        ascending=True, method="first"
    ).le(3)
    return sampled


def _fallback_real_bonds(n_bonds: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source_bond_id": [f"fallback_{i}" for i in range(n_bonds)],
            "source_issuer_id": [f"fallback_issuer_{i//5}" for i in range(n_bonds)],
            "currency": "USD",
            "sector": "unknown",
            "industry": "unknown",
            "rating": "unknown",
            "median_notional": 250000.0,
            "notional_p90": 1000000.0,
            "empirical_trades_per_day": 2.0,
            "zero_trade_day_rate": 0.25,
            "liquidity_rank_global": np.linspace(0.01, 0.99, n_bonds),
            "liquidity_rank_within_issuer": 0.5,
            "liquidity_bucket": "medium",
            "maturity_bucket": "unknown",
            "rating_bucket": "unknown",
        }
    )
