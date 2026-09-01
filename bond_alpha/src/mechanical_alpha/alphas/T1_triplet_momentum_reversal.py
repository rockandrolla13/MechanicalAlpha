"""T1: Triplet momentum/reversal research operator.

This standalone alpha computes observable triplet scores from canonical public
event prices. Selection should be fitted on a training partition by the canonical
runner before scoring validation or test partitions.
"""

from __future__ import annotations

import pandas as pd

from mechanical_alpha.alpha_common import FeatureDefinition
from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.triplets.clocks import build_calendar_clock
from mechanical_alpha.triplets.method import TripletMethodSpec, fit_triplet_method, score_triplet_method


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="T1",
        formula="Spearman-selected lag-anchor-horizon triplet score from clean-price or fair-value state changes",
        source_fields=("events.prediction_timestamp", "events.price", "fair_values.fair_value"),
        clock="calendar_time | event_time | information_time",
        window="train-selected lags and horizons",
        min_observations=20,
        missing_policy="NaN when no selected train triplet or no as-of state exists",
        expected_sign="positive means positive expected future return",
        feature_class="directional",
        point_in_time_dependencies=("selection fitted on training data only", "state sampled by backward as-of join"),
        computational_cost="O(clock_rows * bond_count * searched_triplets)",
    )


def compute(bundle: AlphaInputBundle, *, spec: TripletMethodSpec | None = None, train_fraction: float = 0.7) -> pd.DataFrame:
    """Compute a small deterministic triplet signal using a chronological train split."""

    spec = spec or TripletMethodSpec(min_obs=3, alpha=1.0)
    state = _state_from_bundle(bundle)
    if state.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal"])
    unique_times = pd.Series(pd.to_datetime(state["timestamp"], utc=False).sort_values().unique())
    split_idx = max(1, min(len(unique_times) - 1, int(len(unique_times) * train_fraction)))
    train_end = pd.Timestamp(unique_times.iloc[split_idx - 1])
    train_state = state[state["timestamp"] <= train_end].copy()
    full_clock = build_calendar_clock(state["timestamp"].min(), state["timestamp"].max(), "10min", name="calendar_10min")
    train_clock = build_calendar_clock(train_state["timestamp"].min(), train_state["timestamp"].max(), "10min", name="calendar_10min_train")
    fitted = fit_triplet_method(train_state, train_clock, spec)
    scored = score_triplet_method(state, full_clock, fitted)
    if scored.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal"])
    result = scored.rename(columns={"timestamp": "prediction_timestamp", "triplet_signal": "t1_triplet_signal"})
    issuers = bundle.bonds.set_index("bond_id")["issuer_id"].astype(str).to_dict()
    result["issuer_id"] = result["bond_id"].map(issuers)
    return result[["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal", "component_count"]]


def _state_from_bundle(bundle: AlphaInputBundle) -> pd.DataFrame:
    if bundle.fair_values is not None and not bundle.fair_values.empty:
        frame = bundle.fair_values.rename(columns={"fair_value": "price", "timestamp": "timestamp"}).copy()
        if "issuer_id" not in frame.columns:
            issuers = bundle.bonds.set_index("bond_id")["issuer_id"].astype(str).to_dict()
            frame["issuer_id"] = frame["bond_id"].astype(str).map(issuers)
        return frame[["timestamp", "bond_id", "issuer_id", "price"]].copy()
    frame = bundle.events.rename(columns={"prediction_timestamp": "timestamp"}).copy()
    return frame[["timestamp", "bond_id", "issuer_id", "price"]].copy()

