"""Compatibility wrapper for standalone microstructure alpha files.

New alpha work should live under `mechanical_alpha.alphas`.
This module remains so existing callers can request the current combined frame.
"""

from __future__ import annotations

from functools import reduce
from typing import Iterable

import pandas as pd

from mechanical_alpha.alpha_common import (
    DEFAULT_CALENDAR_WINDOWS,
    DEFAULT_EVENT_WINDOWS,
    DEFAULT_EWMA_HALFLIVES,
    EPSILON,
    FeatureDefinition,
    build_context,
    compute_from_context,
)
from mechanical_alpha.alphas import (
    A16_rfq_scarcity_disagreement,
    A1_rfq_count_imbalance,
    A2_rfq_notional_imbalance,
    A3_buy_sell_intensity,
    A4_last_side_persistence,
    A5_activity_surprise,
    A6_spread_conditioned_flow,
)
from mechanical_alpha.contracts import AlphaInputBundle

ALPHA_MODULES = (
    A1_rfq_count_imbalance,
    A2_rfq_notional_imbalance,
    A3_buy_sell_intensity,
    A4_last_side_persistence,
    A5_activity_surprise,
    A6_spread_conditioned_flow,
    A16_rfq_scarcity_disagreement,
)


def microstructure_feature_registry() -> list[FeatureDefinition]:
    """Return declarations from each standalone alpha file."""

    return [module.describe() for module in ALPHA_MODULES]


def compute_microstructure_features(
    bundle: AlphaInputBundle,
    *,
    event_windows: Iterable[int] = DEFAULT_EVENT_WINDOWS,
    calendar_windows: Iterable[str] = DEFAULT_CALENDAR_WINDOWS,
    ewma_halflives: Iterable[str] = DEFAULT_EWMA_HALFLIVES,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    """Compute the current combined microstructure frame.

    This is intentionally a wrapper.
    Each alpha formula lives in its own `mechanical_alpha.alphas.*` module.
    """

    context = build_context(bundle)
    if context.prediction_grid.empty:
        return context.prediction_grid.copy()
    frames = [
        compute_from_context(
            context,
            module.add_features,
            event_windows=event_windows,
            calendar_windows=calendar_windows,
            ewma_halflives=ewma_halflives,
            epsilon=epsilon,
        )
        for module in ALPHA_MODULES
    ]
    keys = ["prediction_timestamp", "bond_id", "issuer_id"]
    return reduce(lambda left, right: left.merge(right, on=keys, how="outer"), frames).sort_values(keys).reset_index(drop=True)

