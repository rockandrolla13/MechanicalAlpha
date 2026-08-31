"""Canonical schema constants."""

PUBLIC_TRADE_COLUMNS = [
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
]

TRUTH_COLUMNS = [
    "event_id",
    "scenario",
    "timestamp_utc",
    "session_date",
    "latent_fair_value",
    "ou_pressure",
    "permanent_impact_state",
    "ordinary_temporary_impact_state",
    "planted_large_print_state",
    "planted_leadlag_state",
    "latent_mid_without_planted_effects",
    "latent_mid_with_planted_effects",
    "transaction_concession",
    "observation_noise",
    "hawkes_cluster_id",
    "hawkes_parent_event_id",
    "hawkes_generation",
    "hawkes_edge_class",
    "is_immigrant",
    "large_print_threshold",
    "is_large_print",
    "source_leader_event_id",
    "planted_effect_ids",
]

SIDE_BUY = 1
SIDE_SELL = -1
