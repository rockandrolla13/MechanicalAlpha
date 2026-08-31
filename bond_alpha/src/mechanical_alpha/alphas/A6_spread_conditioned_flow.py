"""A6: spread-conditioned flow pressure."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import (
    AlphaContext,
    first_existing_value,
    interaction,
    last_n,
    last_value_percentile,
    latest_before,
    prior,
    quote_value,
    signed_notional_imbalance,
)
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A6",
        formula="flow pressure interacted with latest as-of composite spread, spread percentile, bid/ask asymmetry, disagreement, staleness, and liquidity bucket",
        source_fields=("quotes.timestamp", "quotes.bid", "quotes.ask", "quotes.mid", "events.side", "events.notional"),
        clock="calendar_time | trace_transaction_time",
        window="latest quote before timestamp; flow last_5",
        min_observations=1,
        missing_policy="NaN for unavailable quote fields; flow component still computed when side and notional exist",
        expected_sign="positive flow with wide/stale spreads flags directional pressure under weaker liquidity",
        feature_class="liquidity",
        point_in_time_dependencies=("quote timestamp < prediction timestamp", "flow events < prediction timestamp"),
        computational_cost="O(prediction_rows * log quote_rows + window_rows)",
    )


def compute(bundle: AlphaInputBundle, *, epsilon: float = EPSILON) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, epsilon=epsilon)


def add_features(
    row: dict[str, object],
    context: AlphaContext,
    bond_id: str,
    asof: pd.Timestamp,
    event_windows: object,
    calendar_windows: object,
    ewma_halflives: object,
    epsilon: float,
) -> None:
    latest_quote = latest_before(context.quotes, bond_id, asof)
    recent_trace = last_n(prior(context.traces[context.traces["side"].isin([-1, 1])], bond_id, asof), 5)
    flow = signed_notional_imbalance(recent_trace, epsilon)
    spread = quote_value(latest_quote, "spread")
    bid = quote_value(latest_quote, "bid")
    ask = quote_value(latest_quote, "ask")
    mid = quote_value(latest_quote, "mid")
    staleness = np.nan if latest_quote is None else (asof - pd.Timestamp(latest_quote["timestamp"])).total_seconds()
    prior_quotes = prior(context.quotes, bond_id, asof)
    spread_percentile = last_value_percentile(prior_quotes.get("spread", pd.Series(dtype=float)), spread)
    disagreement = first_existing_value(latest_quote, ("source_disagreement", "composite_source_disagreement", "quote_dispersion"))
    asymmetry = np.nan
    if pd.notna(bid) and pd.notna(ask) and pd.notna(mid) and mid != 0:
        asymmetry = float((ask + bid - 2.0 * mid) / (abs(mid) + epsilon))
    liquidity_bucket = np.nan
    if bond_id in context.bonds.index and "liquidity_bucket" in context.bonds.columns:
        liquidity_bucket = context.bonds.loc[bond_id, "liquidity_bucket"]

    row["a6_trace_last_5_flow_pressure"] = flow
    row["a6_latest_composite_spread"] = spread
    row["a6_latest_spread_percentile"] = spread_percentile
    row["a6_latest_bid_ask_asymmetry"] = asymmetry
    row["a6_latest_composite_disagreement"] = disagreement
    row["a6_latest_composite_staleness_seconds"] = staleness
    row["a6_flow_x_spread"] = interaction(flow, spread)
    row["a6_flow_x_spread_percentile"] = interaction(flow, spread_percentile)
    row["a6_flow_x_composite_staleness"] = interaction(flow, staleness)
    row["a6_liquidity_bucket"] = liquidity_bucket

