"""A16: RFQ scarcity and disagreement."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, first_existing_value, last_n, prior
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A16",
        formula="responder count, scarcity, quote dispersion, latency, no-response rate, firm-up rate, execution rate, and latest indication age",
        source_fields=("rfqs.timestamp", "rfqs.number_of_dealers", "rfqs.response_count", "rfqs.response_latency_ms"),
        clock="rfq_event_time",
        window="last_25",
        min_observations=1,
        missing_policy="NaN for fields absent from the RFQ table; rates require prior RFQs",
        expected_sign="higher scarcity or disagreement means worse liquidity and more uncertainty",
        feature_class="liquidity",
        point_in_time_dependencies=("rfq timestamp < prediction timestamp",),
        computational_cost="O(prediction_rows * window_rows)",
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

