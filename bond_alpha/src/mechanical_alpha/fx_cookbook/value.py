"""Fundamental-value cookbook operators."""

from __future__ import annotations

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def blocked_fundamental_value() -> BlockedStrategy:
    """Return the source-literal fundamental-value blocker."""

    return BlockedStrategy(
        strategy_id="FX_FUNDAMENTAL_VALUE_LITERAL",
        status="BLOCKED_HUMAN",
        reason="The current public bond bundle has no REER or DOLS fundamental-value panel.",
        blocking_decisions=("VALUE-001",),
        missing_inputs=("reer", "fundamental_value_panel"),
    )

