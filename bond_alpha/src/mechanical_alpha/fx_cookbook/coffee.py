"""COFFEE/DTCC positioning cookbook status."""

from __future__ import annotations

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def blocked_coffee_dtcc() -> BlockedStrategy:
    """Return a missing-data blocker for COFFEE/DTCC positioning."""

    return BlockedStrategy(
        strategy_id="COFFEE_DTCC_POSITIONING",
        status="BLOCKED_MISSING_DATA",
        reason="The current public bond bundle has no point-in-time DTCC/COFFEE options positioning fields.",
        blocking_decisions=("COFFEE-001", "COFFEE-002"),
        missing_inputs=("option_delta", "option_ttm", "call_put_notional"),
    )

