"""CFTC reversal cookbook status."""

from __future__ import annotations

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def blocked_cftc_reversal() -> BlockedStrategy:
    """Return a human-decision blocker for CFTC reversal."""

    return BlockedStrategy(
        strategy_id="CFTC_REVERSAL",
        status="BLOCKED_HUMAN",
        reason="The source flags the time-series reversal interpretation as a material decision and current data lack CFTC reports.",
        blocking_decisions=("CFTC-R-001",),
        missing_inputs=("cftc_report_date", "cftc_net_position"),
    )

