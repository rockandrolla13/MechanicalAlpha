"""A6: spread-conditioned flow pressure."""

from __future__ import annotations

from dataclasses import dataclass

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
    within_timedelta,
)
from mechanical_alpha.contracts import AlphaInputBundle

A6_FAST_CALENDAR_WINDOWS = ("1d", "3d")
A6_SLOW_CALENDAR_WINDOWS = ("5d", "10d", "20d", "40d", "60d", "120d")
A6_FAST_TRADE_WINDOWS = (5, 10)
A6_SLOW_TRADE_WINDOWS = (25, 50)
A6_MODEL_VERSION = "0.2.0"


@dataclass(frozen=True)
class SpreadConditionedFlowConfig:
    """Config local to standalone A6."""

    fast_calendar_windows: tuple[str, ...] = A6_FAST_CALENDAR_WINDOWS
    slow_calendar_windows: tuple[str, ...] = A6_SLOW_CALENDAR_WINDOWS
    fast_trade_windows: tuple[int, ...] = A6_FAST_TRADE_WINDOWS
    slow_trade_windows: tuple[int, ...] = A6_SLOW_TRADE_WINDOWS
    flow_measures: tuple[str, ...] = ("notional", "cr01")
    slow_refit_frequency: str = "monthly"
    epsilon: float = EPSILON


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A6",
        formula="fast and slow flow pressure interacted with latest as-of composite spread, spread percentile, bid/ask asymmetry, disagreement, staleness, and liquidity bucket",
        source_fields=("quotes.timestamp", "quotes.bid", "quotes.ask", "quotes.mid", "events.side", "events.notional", "events.cr01"),
        clock="calendar_time | trace_transaction_time",
        window="fast: 1d, 3d, last 5/10 trades; slow: 5d, 10d, 20d, 40d, 60d, 120d, last 25/50 trades",
        min_observations=1,
        missing_policy="NaN for unavailable quote fields; CR01 flow is NaN when event-level CR01 is absent",
        expected_sign="positive flow with wide/stale spreads flags directional risk pressure under weaker liquidity",
        feature_class="liquidity",
        point_in_time_dependencies=("quote timestamp < prediction timestamp", "flow events < prediction timestamp"),
        computational_cost="O(prediction_rows * log quote_rows + window_rows)",
        version=A6_MODEL_VERSION,
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    epsilon: float = EPSILON,
    config: SpreadConditionedFlowConfig | None = None,
) -> pd.DataFrame:
    cfg = config or SpreadConditionedFlowConfig(epsilon=epsilon)
    context = build_context(bundle)
    event_windows = tuple(dict.fromkeys(cfg.fast_trade_windows + cfg.slow_trade_windows))
    calendar_windows = tuple(dict.fromkeys(cfg.fast_calendar_windows + cfg.slow_calendar_windows))
    return compute_from_context(
        context,
        lambda row, ctx, bond_id, asof, event_windows, calendar_windows, ewma_halflives, epsilon: add_features(
            row,
            ctx,
            bond_id,
            asof,
            event_windows,
            calendar_windows,
            ewma_halflives,
            epsilon,
            config=cfg,
        ),
        event_windows=event_windows,
        calendar_windows=calendar_windows,
        epsilon=cfg.epsilon,
    )


def config_from_mapping(payload: dict[str, object]) -> SpreadConditionedFlowConfig:
    return SpreadConditionedFlowConfig(
        fast_calendar_windows=tuple(str(item) for item in payload.get("fast_calendar_windows", A6_FAST_CALENDAR_WINDOWS)),
        slow_calendar_windows=tuple(str(item) for item in payload.get("slow_calendar_windows", A6_SLOW_CALENDAR_WINDOWS)),
        fast_trade_windows=tuple(int(item) for item in payload.get("fast_trade_windows", A6_FAST_TRADE_WINDOWS)),
        slow_trade_windows=tuple(int(item) for item in payload.get("slow_trade_windows", A6_SLOW_TRADE_WINDOWS)),
        flow_measures=tuple(str(item) for item in payload.get("flow_measures", ("notional", "cr01"))),
        slow_refit_frequency=str(payload.get("slow_refit_frequency", "monthly")),
        epsilon=float(payload.get("epsilon", EPSILON)),
    )


def add_features(
    row: dict[str, object],
    context: AlphaContext,
    bond_id: str,
    asof: pd.Timestamp,
    event_windows: object,
    calendar_windows: object,
    ewma_halflives: object,
    epsilon: float,
    config: SpreadConditionedFlowConfig | None = None,
) -> None:
    cfg = config or SpreadConditionedFlowConfig(epsilon=epsilon)
    latest_quote = latest_before(context.quotes, bond_id, asof)
    valid_trace = prior(context.traces[context.traces["side"].isin([-1, 1])], bond_id, asof)
    flow = _signed_measure_imbalance(last_n(valid_trace, 5), "notional", epsilon)
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
    _add_family_features(row, valid_trace, asof, cfg, "fast", cfg.fast_calendar_windows, cfg.fast_trade_windows, spread, spread_percentile, staleness)
    _add_family_features(row, valid_trace, asof, cfg, "slow", cfg.slow_calendar_windows, cfg.slow_trade_windows, spread, spread_percentile, staleness)


def _add_family_features(
    row: dict[str, object],
    valid_trace: pd.DataFrame,
    asof: pd.Timestamp,
    config: SpreadConditionedFlowConfig,
    family: str,
    calendar_windows: tuple[str, ...],
    trade_windows: tuple[int, ...],
    spread: float,
    spread_percentile: float,
    staleness: float,
) -> None:
    for window in trade_windows:
        frame = last_n(valid_trace, int(window))
        _add_flow_interactions(row, frame, asof, family, "trade", f"last_{window}", config, spread, spread_percentile, staleness)
    for window in calendar_windows:
        frame = within_timedelta(valid_trace, asof, _to_timedelta(window))
        _add_flow_interactions(row, frame, asof, family, "calendar", str(window), config, spread, spread_percentile, staleness)


def _add_flow_interactions(
    row: dict[str, object],
    frame: pd.DataFrame,
    asof: pd.Timestamp,
    family: str,
    clock: str,
    window: str,
    config: SpreadConditionedFlowConfig,
    spread: float,
    spread_percentile: float,
    staleness: float,
) -> None:
    for measure in config.flow_measures:
        flow = _signed_measure_imbalance(frame, measure, config.epsilon)
        prefix = f"a6_{family}_{clock}_{window}_{measure}"
        row[f"{prefix}_flow_pressure"] = flow
        row[f"{prefix}_flow_x_spread"] = interaction(flow, spread)
        row[f"{prefix}_flow_x_spread_percentile"] = interaction(flow, spread_percentile)
        row[f"{prefix}_flow_x_composite_staleness"] = interaction(flow, staleness)
        row[f"{prefix}_observation_count"] = float(len(frame))
        last_ts = frame["timestamp"].max() if not frame.empty else pd.NaT
        row[f"{prefix}_last_observation_timestamp"] = last_ts
        row[f"{prefix}_staleness_seconds"] = np.nan if pd.isna(last_ts) else float((asof - pd.Timestamp(last_ts)).total_seconds())
        row[f"{prefix}_quality_flag"] = _quality_flag(frame, measure)
        row[f"{prefix}_model_version"] = A6_MODEL_VERSION


def _signed_measure_imbalance(frame: pd.DataFrame, measure: str, epsilon: float) -> float:
    if frame.empty or "side" not in frame.columns or measure not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[measure], errors="coerce")
    sides = pd.to_numeric(frame["side"], errors="coerce")
    mask = values.notna() & sides.isin([-1, 1])
    if not mask.any():
        return np.nan
    gross = values[mask].abs().sum()
    signed = (sides[mask] * values[mask].abs()).sum()
    return float(signed / (gross + epsilon))


def _quality_flag(frame: pd.DataFrame, measure: str) -> str:
    if frame.empty:
        return "no_observations"
    if measure not in frame.columns or pd.to_numeric(frame[measure], errors="coerce").notna().sum() == 0:
        return f"missing_{measure}"
    return "ok"


def _to_timedelta(window: str) -> pd.Timedelta:
    text = str(window).strip().lower()
    if text.endswith("d") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="D")
    if text.endswith("h") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="h")
    if text.endswith("m") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="m")
    return pd.Timedelta(text)
