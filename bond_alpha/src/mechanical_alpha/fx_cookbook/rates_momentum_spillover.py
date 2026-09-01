"""Rates momentum spill-over operators."""

from __future__ import annotations

import pandas as pd

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def compute_rates_momentum_spillover(rate_differential: pd.DataFrame, *, lookback: int, standardization_window: int) -> pd.DataFrame:
    """Compute standardized rate-differential momentum."""

    if lookback <= 0 or standardization_window <= 1:
        raise ValueError("lookback must be positive and standardization_window must exceed one")
    change = rate_differential - rate_differential.shift(lookback)
    scale = change.rolling(standardization_window, min_periods=2).std().replace(0.0, pd.NA)
    return change / scale


def blocked_rates_spillover() -> BlockedStrategy:
    """Return a missing-data blocker for current public bond bundles."""

    return BlockedStrategy(
        strategy_id="RATES_MOMENTUM_SPILLOVER",
        status="BLOCKED_MISSING_DATA",
        reason="Point-in-time rate or curve-factor inputs are not guaranteed in the portable alpha bundle.",
        missing_inputs=("external_factors:rates", "curve_changes"),
    )

