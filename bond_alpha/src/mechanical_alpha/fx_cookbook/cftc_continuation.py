"""CFTC continuation cookbook status."""

from __future__ import annotations

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def blocked_cftc_continuation() -> BlockedStrategy:
    """Return a missing-data blocker for CFTC continuation."""

    return BlockedStrategy(
        strategy_id="CFTC_CONTINUATION",
        status="BLOCKED_MISSING_DATA",
        reason="The current public bond bundle has no CFTC COT positioning reports.",
        missing_inputs=("cftc_report_date", "cftc_net_position"),
    )

