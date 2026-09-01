"""Carry cookbook operators and blocked adapters."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def compute_fx_carry(spot: pd.DataFrame, forward: pd.DataFrame, *, quote_orientation: str) -> pd.DataFrame:
    """Compute FX carry from spot and forward panels with explicit orientation."""

    if quote_orientation == "base_per_quote":
        return forward / spot.replace(0.0, np.nan) - 1.0
    if quote_orientation == "quote_per_base":
        return spot / forward.replace(0.0, np.nan) - 1.0
    raise ValueError("quote_orientation must be base_per_quote or quote_per_base")


def smooth_carry(carry: pd.DataFrame, *, window: int) -> pd.DataFrame:
    """Smooth carry with a trailing mean."""

    if window <= 0:
        raise ValueError("window must be positive")
    return carry.rolling(window=window, min_periods=1).mean()


def blocked_carry() -> BlockedStrategy:
    """Return the source-literal carry blocker."""

    return BlockedStrategy(
        strategy_id="FX_CARRY_LITERAL",
        status="BLOCKED_HUMAN",
        reason="Carry needs explicit quote orientation, financing convention, and bond carry/roll-down translation.",
        blocking_decisions=("CARRY-001", "CARRY-002", "CARRY-003"),
        missing_inputs=("fx_forward", "financing_curve"),
    )

