"""A3: buy/sell intensity pressure."""

from __future__ import annotations

from math import log

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_EWMA_HALFLIVES, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, key, nan_if_no_obs, prior
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A3",
        formula="elapsed-time EWMA buy intensity, sell intensity, difference, ratio, and log ratio",
        source_fields=("rfqs.side", "rfqs.timestamp", "events.side", "events.prediction_timestamp"),
        clock="calendar_time",
        window="30m, 2h half-life",
        min_observations=1,
        missing_policy="NaN when no prior observations exist for the source",
        expected_sign="higher buy-minus-sell or log ratio means customer-buy pressure",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp", "EWMA weights use elapsed time"),
        computational_cost="O(prediction_rows * prior_rows)",
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    ewma_halflives: tuple[str, ...] = DEFAULT_EWMA_HALFLIVES,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, ewma_halflives=ewma_halflives, epsilon=epsilon)


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
    for source_name, source in {"rfq": context.rfqs, "trace": context.traces}.items():
        valid_prior = prior(source[source["side"].isin([-1, 1])], bond_id, asof)
        for half_life in ewma_halflives:
            buy_intensity = _ewma_intensity(valid_prior[valid_prior["side"] == 1], asof, pd.Timedelta(str(half_life)))
            sell_intensity = _ewma_intensity(valid_prior[valid_prior["side"] == -1], asof, pd.Timedelta(str(half_life)))
            prefix = key("a3", source_name, half_life)
            row[f"{prefix}_buy_intensity"] = buy_intensity
            row[f"{prefix}_sell_intensity"] = sell_intensity
            row[f"{prefix}_intensity_difference"] = nan_if_no_obs(buy_intensity, sell_intensity, buy_intensity - sell_intensity)
            row[f"{prefix}_intensity_ratio"] = nan_if_no_obs(
                buy_intensity, sell_intensity, (buy_intensity + epsilon) / (sell_intensity + epsilon)
            )
            row[f"{prefix}_log_intensity_ratio"] = nan_if_no_obs(
                buy_intensity, sell_intensity, log((buy_intensity + epsilon) / (sell_intensity + epsilon))
            )


def _ewma_intensity(frame: pd.DataFrame, asof: pd.Timestamp, half_life: pd.Timedelta) -> float:
    if frame.empty:
        return np.nan
    ages = (asof - frame["timestamp"]).dt.total_seconds().to_numpy(dtype=float)
    half_life_seconds = max(float(half_life.total_seconds()), 1.0)
    weights = np.exp(-np.log(2.0) * ages / half_life_seconds)
    return float(np.nansum(weights) / half_life_seconds)

