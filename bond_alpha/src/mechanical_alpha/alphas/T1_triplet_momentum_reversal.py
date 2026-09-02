"""T1: Triplet momentum/reversal research operator.

This standalone alpha computes observable triplet scores from canonical public
event prices. Selection should be fitted on a training partition by the canonical
runner before scoring validation or test partitions.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from mechanical_alpha.alpha_common import FeatureDefinition
from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.triplets.clocks import build_calendar_clock, build_event_clock, build_information_clock
from mechanical_alpha.triplets.method import TripletMethodSpec, fit_triplet_method, score_triplet_method

T1_MODEL_VERSION = "0.2.0"


@dataclass(frozen=True)
class TripletAlphaConfig:
    """Portable config for the standalone T1 alpha."""

    clock_type: str = "calendar"
    calendar_frequency: str = "10min"
    event_threshold: int = 10
    information_threshold: float = 1_000_000.0
    information_activity_column: str = "notional"
    lags: tuple[int, ...] = (1, 2)
    horizons: tuple[int, ...] = (1, 2)
    anchors: tuple[int, ...] = (0,)
    target_type: str = "clean_price"
    alpha: float = 0.05
    min_obs: int = 20
    multiplicity_method: str = "holm"
    value_col: str = "price"
    train_fraction: float = 0.70

    def method_spec(self) -> TripletMethodSpec:
        return TripletMethodSpec(
            lags=self.lags,
            horizons=self.horizons,
            anchors=self.anchors,
            target_type=self.target_type,
            alpha=self.alpha,
            min_obs=self.min_obs,
            multiplicity_method=self.multiplicity_method,
            value_col=self.value_col,
        )


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
        version=T1_MODEL_VERSION,
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    spec: TripletMethodSpec | None = None,
    train_fraction: float = 0.7,
    config: TripletAlphaConfig | None = None,
) -> pd.DataFrame:
    """Compute a small deterministic triplet signal using a chronological train split."""

    cfg = config or TripletAlphaConfig(train_fraction=train_fraction)
    if spec is None:
        spec = cfg.method_spec() if config is not None else TripletMethodSpec(min_obs=3, alpha=1.0)
    state = _state_from_bundle(bundle)
    if state.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal"])
    unique_times = pd.Series(pd.to_datetime(state["timestamp"], utc=False).sort_values().unique())
    split_idx = max(1, min(len(unique_times) - 1, int(len(unique_times) * cfg.train_fraction)))
    train_end = pd.Timestamp(unique_times.iloc[split_idx - 1])
    train_state = state[state["timestamp"] <= train_end].copy()
    full_clock = _build_clock(state, cfg, suffix="full")
    train_clock = _build_clock(train_state, cfg, suffix="train")
    fitted = fit_triplet_method(train_state, train_clock, spec)
    scored = score_triplet_method(state, full_clock, fitted)
    if scored.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal"])
    result = scored.rename(columns={"timestamp": "prediction_timestamp", "triplet_signal": "t1_triplet_signal"})
    issuers = bundle.bonds.set_index("bond_id")["issuer_id"].astype(str).to_dict()
    result["issuer_id"] = result["bond_id"].map(issuers)
    return result[["prediction_timestamp", "bond_id", "issuer_id", "t1_triplet_signal", "component_count"]]


def config_from_mapping(payload: dict[str, object]) -> TripletAlphaConfig:
    """Build a T1 config from YAML."""

    return TripletAlphaConfig(
        clock_type=str(payload.get("clock_type", "calendar")),
        calendar_frequency=str(payload.get("calendar_frequency", "10min")),
        event_threshold=int(payload.get("event_threshold", 10)),
        information_threshold=float(payload.get("information_threshold", 1_000_000.0)),
        information_activity_column=str(payload.get("information_activity_column", "notional")),
        lags=tuple(int(item) for item in payload.get("lags", (1, 2))),
        horizons=tuple(int(item) for item in payload.get("horizons", (1, 2))),
        anchors=tuple(int(item) for item in payload.get("anchors", (0,))),
        target_type=str(payload.get("target_type", "clean_price")),
        alpha=float(payload.get("alpha", 0.05)),
        min_obs=int(payload.get("min_obs", 20)),
        multiplicity_method=str(payload.get("multiplicity_method", "holm")),
        value_col=str(payload.get("value_col", "price")),
        train_fraction=float(payload.get("train_fraction", 0.70)),
    )


def _build_clock(state: pd.DataFrame, config: TripletAlphaConfig, *, suffix: str) -> object:
    if state.empty:
        return build_calendar_clock(pd.Timestamp.min, pd.Timestamp.min, config.calendar_frequency, name=f"calendar_{suffix}")
    if config.clock_type == "calendar":
        return build_calendar_clock(
            state["timestamp"].min(),
            state["timestamp"].max(),
            config.calendar_frequency,
            name=f"calendar_{config.calendar_frequency}_{suffix}",
        )
    if config.clock_type == "event":
        return build_event_clock(state, config.event_threshold, name=f"event_{config.event_threshold}_{suffix}")
    if config.clock_type == "information":
        activity = config.information_activity_column
        if activity not in state.columns:
            raise ValueError(f"information activity column is unavailable: {activity}")
        return build_information_clock(
            state,
            config.information_threshold,
            activity=activity,
            name=f"information_{activity}_{config.information_threshold:g}_{suffix}",
        )
    raise ValueError(f"unknown triplet clock_type: {config.clock_type}")


def _state_from_bundle(bundle: AlphaInputBundle) -> pd.DataFrame:
    if bundle.fair_values is not None and not bundle.fair_values.empty:
        frame = bundle.fair_values.rename(columns={"fair_value": "price", "timestamp": "timestamp"}).copy()
        if "issuer_id" not in frame.columns:
            issuers = bundle.bonds.set_index("bond_id")["issuer_id"].astype(str).to_dict()
            frame["issuer_id"] = frame["bond_id"].astype(str).map(issuers)
        return frame[["timestamp", "bond_id", "issuer_id", "price"]].copy()
    frame = bundle.events.rename(columns={"prediction_timestamp": "timestamp"}).copy()
    optional = [column for column in ("notional", "dv01", "cr01") if column in frame.columns]
    return frame[["timestamp", "bond_id", "issuer_id", "price", *optional]].copy()
