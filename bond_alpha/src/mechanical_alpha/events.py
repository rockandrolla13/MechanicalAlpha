"""Canonical point-in-time event records for corporate-bond alpha labels.

Canonical side convention:
customer buy = +1
customer sell = -1

For executed RFQs:
dealer_inventory_change = -customer_side * executed_notional
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd


CUSTOMER_BUY = 1
CUSTOMER_SELL = -1
SIDE_UNKNOWN = 0
VALID_CUSTOMER_SIDES = frozenset({CUSTOMER_BUY, CUSTOMER_SELL})


class RfqStage(str, Enum):
    INQUIRY = "inquiry"
    DEALER_RESPONSE = "dealer_response"
    FIRM_UP = "firm_up"
    EXECUTION = "execution"
    EXPIRY = "expiry"
    NO_TRADE = "no_trade"


class TraceSideQuality(str, Enum):
    OBSERVED = "observed"
    CLASSIFIED = "classified"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class EventTimestamps:
    """Timestamps retained for point-in-time safety."""

    source_event_time: pd.Timestamp
    receive_time: pd.Timestamp | None = None
    effective_time: pd.Timestamp | None = None
    publication_time: pd.Timestamp | None = None
    revision_time: pd.Timestamp | None = None
    feature_calculation_time: pd.Timestamp | None = None


@dataclass(frozen=True)
class RfqEvent:
    rfq_id: str
    stage: RfqStage
    bond_id: str
    issuer_id: str | None
    timestamps: EventTimestamps
    customer_side: int | None = None
    requested_notional: float | None = None
    executed_notional: float | None = None
    execution_price: float | None = None
    responded: bool | None = None
    firmed_up: bool | None = None
    won: bool | None = None
    executed: bool | None = None
    response_latency_ms: float | None = None
    quoted_spread: float | None = None
    quoted_price: float | None = None
    venue: str | None = None
    protocol: str | None = None
    request_type: str | None = None

    @property
    def dealer_inventory_change(self) -> float | None:
        if self.customer_side is None or self.executed_notional is None:
            return None
        return dealer_inventory_change(self.customer_side, self.executed_notional)


@dataclass(frozen=True)
class TraceTrade:
    trade_id: str
    bond_id: str
    issuer_id: str | None
    timestamps: EventTimestamps
    price: float
    notional: float
    customer_side: int | None = None
    side_quality: TraceSideQuality = TraceSideQuality.UNAVAILABLE
    is_interdealer: bool | None = None
    raw_side: str | None = None


@dataclass(frozen=True)
class CompositeSnapshot:
    snapshot_id: str
    bond_id: str
    timestamps: EventTimestamps
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    spread: float | None = None
    evaluated_price: float | None = None
    source: str | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceSnapshot:
    reference_id: str
    reference_type: str
    timestamps: EventTimestamps
    value: float
    tenor: str | None = None
    source: str | None = None
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SecurityMasterSnapshot:
    snapshot_id: str
    bond_id: str
    timestamps: EventTimestamps
    issuer_id: str | None = None
    isin: str | None = None
    sector: str | None = None
    rating: str | None = None
    maturity: pd.Timestamp | None = None
    duration: float | None = None
    currency: str | None = None
    seniority: str | None = None
    security_type: str | None = None
    callable_flag: bool | None = None
    convertible_flag: bool | None = None


def normalize_customer_side(value: Any) -> int:
    """Normalize customer side to +1 buy, -1 sell, or raise on ambiguity."""

    if value in (CUSTOMER_BUY, CUSTOMER_SELL):
        return int(value)
    text = str(value).strip().lower()
    buy_values = {"buy", "b", "customer_buy", "client_buy", "client buys", "customer buys"}
    sell_values = {"sell", "s", "customer_sell", "client_sell", "client sells", "customer sells"}
    if text in buy_values:
        return CUSTOMER_BUY
    if text in sell_values:
        return CUSTOMER_SELL
    raise ValueError(f"cannot normalize customer side from {value!r}")


def dealer_inventory_change(customer_side: int, executed_notional: float) -> float:
    """Return dealer signed inventory change for an executed RFQ."""

    side = normalize_customer_side(customer_side)
    notional = float(executed_notional)
    if notional < 0:
        raise ValueError("executed_notional must be nonnegative")
    return -side * notional


def require_trace_side_quality(side_quality: str | TraceSideQuality) -> TraceSideQuality:
    quality = TraceSideQuality(side_quality)
    if quality not in {TraceSideQuality.OBSERVED, TraceSideQuality.CLASSIFIED}:
        raise ValueError("TRACE side must be observed or separately validated before signed labels are used")
    return quality

