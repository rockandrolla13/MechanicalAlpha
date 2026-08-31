"""Small schema contracts for public Alpha Factory data."""

from __future__ import annotations

from dataclasses import dataclass


PUBLIC_TRADE_COLUMNS = (
    "event_id",
    "timestamp_utc",
    "session_date",
    "synthetic_bond_id",
    "synthetic_issuer_id",
    "side",
    "notional",
    "price",
    "is_interdealer",
    "trade_type",
    "venue_bucket",
    "reporting_delay_ms",
    "currency",
)

TARGET_TYPES = (
    "future_clean_price_move",
    "future_issuer_residual_move",
    "next_event_side",
    "future_signed_flow",
)


@dataclass(frozen=True)
class MarketDataSchema:
    """Required public trade columns for alpha development."""

    required_columns: tuple[str, ...] = PUBLIC_TRADE_COLUMNS
    side_convention: str = "customer buy = +1, customer sell = -1"


@dataclass(frozen=True)
class TargetSchema:
    """Separate target families.

    Return alpha, flow toxicity, and relative-value targets are deliberately
    named separately so later modeling cannot collapse them by accident.
    """

    target_types: tuple[str, ...] = TARGET_TYPES
    horizons: tuple[str, ...] = ("30m", "2h", "1d", "5d")


def public_trade_columns() -> tuple[str, ...]:
    return PUBLIC_TRADE_COLUMNS


def target_types() -> tuple[str, ...]:
    return TARGET_TYPES
