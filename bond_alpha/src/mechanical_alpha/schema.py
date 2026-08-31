"""Canonical schemas for alpha research inputs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Availability(str, Enum):
    """Availability state for a canonical input or factor."""

    DIRECT = "directly_available"
    DERIVABLE = "derivable"
    PARTIAL = "partially_available"
    UNAVAILABLE = "unavailable"
    AMBIGUOUS = "ambiguous"


class SideConvention(str, Enum):
    """Supported side conventions at the alpha seam."""

    DEALER = "dealer_perspective"
    CUSTOMER = "customer_perspective"
    SOURCE = "source_defined"


@dataclass(frozen=True)
class TableSchema:
    """Required and optional columns for one canonical table."""

    name: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()

    def known_columns(self) -> set[str]:
        return set(self.required).union(self.optional)


BONDS_SCHEMA = TableSchema(
    name="bonds",
    required=("bond_id", "issuer_id"),
    optional=(
        "currency",
        "sector",
        "industry",
        "rating",
        "coupon",
        "maturity_date",
        "years_to_maturity",
        "duration",
        "convexity",
        "issue_size",
        "amount_outstanding",
        "seniority",
        "callable_flag",
        "liquidity_bucket",
        "maturity_bucket",
        "rating_bucket",
    ),
)

EVENTS_SCHEMA = TableSchema(
    name="events",
    required=("event_id", "prediction_timestamp", "bond_id", "issuer_id", "side", "price", "notional"),
    optional=(
        "event_timestamp",
        "receive_timestamp",
        "publication_timestamp",
        "revision_timestamp",
        "session_date",
        "is_interdealer",
        "trade_type",
        "venue",
        "yield",
        "oas",
        "source_table",
    ),
)

QUOTES_SCHEMA = TableSchema(
    name="quotes",
    required=("quote_id", "timestamp", "bond_id", "bid", "ask"),
    optional=("mid", "bid_size", "ask_size", "contributor_count", "publication_timestamp", "revision_timestamp"),
)

FAIR_VALUES_SCHEMA = TableSchema(
    name="fair_values",
    required=("timestamp", "bond_id", "fair_value"),
    optional=("spread", "oas", "yield", "duration", "publication_timestamp", "revision_timestamp"),
)

RFQS_SCHEMA = TableSchema(
    name="rfqs",
    required=("rfq_id", "timestamp", "bond_id", "side", "size"),
    optional=("issuer_id", "venue", "protocol", "number_of_dealers", "request_type", "quote_time", "fill_flag"),
)

EXTERNAL_FACTORS_SCHEMA = TableSchema(
    name="external_factors",
    required=("timestamp", "factor_id", "value"),
    optional=("publication_timestamp", "revision_timestamp", "source"),
)

TRUTH_FORBIDDEN_COLUMNS = frozenset(
    {
        "truth",
        "truth_label",
        "latent_fair_value",
        "latent_mid",
        "latent_mid_with_planted_effects",
        "latent_mid_without_planted_effects",
        "planted_effect_ids",
        "planted_large_print_state",
        "planted_leadlag_state",
        "hawkes_parent_event_id",
        "hawkes_cluster_id",
    }
)

SOURCE_IDENTIFIER_COLUMNS = frozenset(
    {
        "source_bond_id",
        "source_issuer_id",
        "cusip",
        "isin",
        "client_id",
        "dealer_id",
        "account_id",
    }
)

