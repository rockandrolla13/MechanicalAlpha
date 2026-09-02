"""A16: RFQ scarcity and disagreement."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, first_existing_value, last_n, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle

A16_FAST_CALENDAR_WINDOWS = ("1d", "3d")
A16_SLOW_CALENDAR_WINDOWS = ("5d", "10d", "20d", "40d", "60d", "120d")
A16_FAST_RFQ_WINDOWS = (5, 10)
A16_SLOW_RFQ_WINDOWS = (25, 50)
A16_MODEL_VERSION = "0.2.0"


@dataclass(frozen=True)
class RFQScarcityConfig:
    """Config local to standalone A16."""

    fast_calendar_windows: tuple[str, ...] = A16_FAST_CALENDAR_WINDOWS
    slow_calendar_windows: tuple[str, ...] = A16_SLOW_CALENDAR_WINDOWS
    fast_rfq_windows: tuple[int, ...] = A16_FAST_RFQ_WINDOWS
    slow_rfq_windows: tuple[int, ...] = A16_SLOW_RFQ_WINDOWS
    slow_refit_frequency: str = "monthly"
    epsilon: float = EPSILON


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A16",
        formula="fast and slow responder scarcity, quote dispersion, latency, no-response rate, firm-up rate, execution rate, and latest indication age",
        source_fields=("rfqs.timestamp", "rfqs.number_of_dealers", "rfqs.response_count", "rfqs.response_latency_ms"),
        clock="rfq_event_time | calendar_time",
        window="fast: 1d, 3d, last 5/10 RFQs; slow: 5d, 10d, 20d, 40d, 60d, 120d, last 25/50 RFQs",
        min_observations=1,
        missing_policy="NaN for fields absent from the RFQ table; rates require prior RFQs",
        expected_sign="higher scarcity or disagreement means worse liquidity and more uncertainty",
        feature_class="liquidity",
        point_in_time_dependencies=("rfq timestamp < prediction timestamp",),
        computational_cost="O(prediction_rows * window_rows)",
        version=A16_MODEL_VERSION,
    )


def compute(bundle: AlphaInputBundle, *, epsilon: float = EPSILON, config: RFQScarcityConfig | None = None) -> pd.DataFrame:
    cfg = config or RFQScarcityConfig(epsilon=epsilon)
    context = build_context(bundle)
    event_windows = tuple(dict.fromkeys(cfg.fast_rfq_windows + cfg.slow_rfq_windows))
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


def config_from_mapping(payload: dict[str, object]) -> RFQScarcityConfig:
    return RFQScarcityConfig(
        fast_calendar_windows=tuple(str(item) for item in payload.get("fast_calendar_windows", A16_FAST_CALENDAR_WINDOWS)),
        slow_calendar_windows=tuple(str(item) for item in payload.get("slow_calendar_windows", A16_SLOW_CALENDAR_WINDOWS)),
        fast_rfq_windows=tuple(int(item) for item in payload.get("fast_rfq_windows", A16_FAST_RFQ_WINDOWS)),
        slow_rfq_windows=tuple(int(item) for item in payload.get("slow_rfq_windows", A16_SLOW_RFQ_WINDOWS)),
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
    config: RFQScarcityConfig | None = None,
) -> None:
    cfg = config or RFQScarcityConfig(epsilon=epsilon)
    prior_rows = prior(context.rfqs, bond_id, asof)
    recent = last_n(prior_rows, 25)
    latest = None if prior_rows.empty else prior_rows.iloc[-1]

    responders = first_existing_value(latest, ("response_count", "number_of_responders", "observable_responders"))
    dealers = first_existing_value(latest, ("number_of_dealers", "dealer_count"))
    quote_dispersion = first_existing_value(latest, ("quote_dispersion", "quote_price_dispersion", "quoted_spread_dispersion"))
    latency = first_existing_value(latest, ("response_latency_ms", "quote_latency_ms"))
    executable_ts = first_existing_value(latest, ("quote_time", "latest_executable_timestamp"))
    executable_age = np.nan
    if pd.notna(executable_ts):
        executable_age = (asof - pd.Timestamp(executable_ts)).total_seconds()

    row["a16_latest_response_count"] = responders
    row["a16_latest_response_scarcity"] = np.nan if pd.isna(responders) else 1.0 / (float(responders) + 1.0)
    row["a16_latest_dealer_count"] = dealers
    row["a16_latest_quote_dispersion"] = quote_dispersion
    row["a16_latest_response_latency_ms"] = latency
    row["a16_latest_executable_indication_age_seconds"] = executable_age
    row["a16_no_response_rate_last_25"] = _rate_from_bool_columns(recent, ("responded",), invert=True, epsilon=epsilon)
    row["a16_firmup_rate_last_25"] = _rate_from_bool_columns(recent, ("firmed_up", "firm_up"), invert=False, epsilon=epsilon)
    row["a16_execution_rate_last_25"] = _rate_from_bool_columns(recent, ("executed", "fill_flag"), invert=False, epsilon=epsilon)
    _add_family_rates(row, prior_rows, asof, "fast", cfg.fast_calendar_windows, cfg.fast_rfq_windows, cfg)
    _add_family_rates(row, prior_rows, asof, "slow", cfg.slow_calendar_windows, cfg.slow_rfq_windows, cfg)


def _add_family_rates(
    row: dict[str, object],
    prior_rows: pd.DataFrame,
    asof: pd.Timestamp,
    family: str,
    calendar_windows: tuple[str, ...],
    rfq_windows: tuple[int, ...],
    config: RFQScarcityConfig,
) -> None:
    for window in rfq_windows:
        _add_window_rates(row, last_n(prior_rows, int(window)), family, "event", f"last_{window}", config)
    for window in calendar_windows:
        _add_window_rates(row, within_timedelta(prior_rows, asof, _to_timedelta(window)), family, "calendar", str(window), config)


def _add_window_rates(
    row: dict[str, object],
    frame: pd.DataFrame,
    family: str,
    clock: str,
    window: str,
    config: RFQScarcityConfig,
) -> None:
    prefix = f"a16_{family}_{clock}_{window}"
    row[f"{prefix}_no_response_rate"] = _rate_from_bool_columns(frame, ("responded",), invert=True, epsilon=config.epsilon)
    row[f"{prefix}_firmup_rate"] = _rate_from_bool_columns(frame, ("firmed_up", "firm_up"), invert=False, epsilon=config.epsilon)
    row[f"{prefix}_execution_rate"] = _rate_from_bool_columns(frame, ("executed", "fill_flag"), invert=False, epsilon=config.epsilon)
    row[f"{prefix}_mean_response_count"] = _mean_first_existing(frame, ("response_count", "number_of_responders", "observable_responders"))
    row[f"{prefix}_mean_quote_dispersion"] = _mean_first_existing(frame, ("quote_dispersion", "quote_price_dispersion", "quoted_spread_dispersion"))
    row[f"{prefix}_mean_latency_ms"] = _mean_first_existing(frame, ("response_latency_ms", "quote_latency_ms"))
    row[f"{prefix}_observation_count"] = float(len(frame))
    row[f"{prefix}_quality_flag"] = "no_observations" if frame.empty else "ok"
    row[f"{prefix}_model_version"] = A16_MODEL_VERSION


def _rate_from_bool_columns(frame: pd.DataFrame, columns: tuple[str, ...], *, invert: bool, epsilon: float) -> float:
    if frame.empty:
        return np.nan
    for column in columns:
        if column in frame.columns:
            values = frame[column].dropna().astype(bool)
            if values.empty:
                return np.nan
            positives = (~values).sum() if invert else values.sum()
            return float(positives / (len(values) + epsilon))
    return np.nan


def _mean_first_existing(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    if frame.empty:
        return np.nan
    for column in columns:
        if column in frame.columns:
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if values.empty:
                return np.nan
            return float(values.mean())
    return np.nan


def _to_timedelta(window: str) -> pd.Timedelta:
    text = str(window).strip().lower()
    if text.endswith("d") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="D")
    if text.endswith("h") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="h")
    if text.endswith("m") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="m")
    return pd.Timedelta(text)
