"""A1: RFQ and TRACE count imbalance."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_CALENDAR_WINDOWS, DEFAULT_EVENT_WINDOWS, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, filter_event_kind, filter_firm_inquiries, key, last_n, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle


@dataclass(frozen=True)
class CountImbalanceConfig:
    """Configuration for fitted asymmetric count/risk-count imbalance."""

    event_windows: tuple[int, ...] = DEFAULT_EVENT_WINDOWS
    calendar_windows: tuple[str, ...] = DEFAULT_CALENDAR_WINDOWS
    risk_measures: tuple[str, ...] = ("count", "cr01")
    side_weight_mode: str = "inverse_market_share"
    epsilon: float = EPSILON


@dataclass(frozen=True)
class SideWeights:
    """Frozen buy/sell weights for one source and measure."""

    buy_weight: float
    sell_weight: float
    buy_total: float
    sell_total: float
    source: str
    measure: str
    method: str = "inverse_market_share"


@dataclass(frozen=True)
class CountImbalanceArtifact:
    """Train-fitted side weights used to score A1."""

    config: CountImbalanceConfig
    weights: dict[str, SideWeights] = field(default_factory=dict)


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A1",
        formula="(w_buy * buy_measure_w - w_sell * sell_measure_w) / (w_buy * buy_measure_w + w_sell * sell_measure_w + epsilon)",
        source_fields=("rfqs.side", "rfqs.timestamp", "rfqs.cr01", "events.side", "events.prediction_timestamp", "events.cr01"),
        clock="calendar_time | rfq_event_time | trace_transaction_time",
        window="configurable event and calendar windows",
        min_observations=1,
        missing_policy="NaN when source table, valid side, or requested risk measure is unavailable; fitted weights are frozen from training data",
        expected_sign="positive means recent customer-buy pressure after adjusting for market side drift",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp", "side weights fitted on training rows only"),
        computational_cost="O(prediction_rows * window_rows)",
        version="0.2.0",
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    event_windows: tuple[int, ...] = DEFAULT_EVENT_WINDOWS,
    calendar_windows: tuple[str, ...] = DEFAULT_CALENDAR_WINDOWS,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, event_windows=event_windows, calendar_windows=calendar_windows, epsilon=epsilon)


def fit(
    bundle: AlphaInputBundle,
    *,
    config: CountImbalanceConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> CountImbalanceArtifact:
    """Fit asymmetric buy/sell weights from training rows only."""

    cfg = config or CountImbalanceConfig()
    context = build_context(bundle)
    weights: dict[str, SideWeights] = {}
    for source_name, source in _sources(context).items():
        training = _training_rows(source, train_end)
        for measure in cfg.risk_measures:
            weights[f"{source_name}:{measure}"] = _fit_side_weights(training, source_name, measure, cfg)
    return CountImbalanceArtifact(config=cfg, weights=weights)


def score(bundle: AlphaInputBundle, artifact: CountImbalanceArtifact) -> pd.DataFrame:
    """Score A1 with frozen train-fitted side weights."""

    context = build_context(bundle)
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
            artifact=artifact,
        ),
        event_windows=artifact.config.event_windows,
        calendar_windows=artifact.config.calendar_windows,
        epsilon=artifact.config.epsilon,
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
    artifact: CountImbalanceArtifact | None = None,
) -> None:
    sources = _sources(context)
    for source_name, source in sources.items():
        for window in event_windows:
            hist = last_n(prior(source, bond_id, asof), int(window))
            _write_count(row, source_name, f"last_{window}", hist, epsilon, artifact)
        for window in calendar_windows:
            hist = within_timedelta(prior(source, bond_id, asof), asof, pd.Timedelta(str(window)))
            _write_count(row, source_name, str(window), hist, epsilon, artifact)


def _sources(context: AlphaContext) -> dict[str, pd.DataFrame]:
    return {
        "rfq_all_inquiries": context.rfqs,
        "rfq_firm_inquiries": filter_firm_inquiries(context.rfqs),
        "rfq_firm_ups": filter_event_kind(context.rfqs, ("firm_up", "firm-up", "firmup")),
        "rfq_executions": filter_event_kind(context.rfqs, ("execution", "executed")),
        "trace_side_valid": context.traces[context.traces["side"].isin([-1, 1])],
    }


def _write_count(
    row: dict[str, object],
    source_name: str,
    window_name: str,
    hist: pd.DataFrame,
    epsilon: float,
    artifact: CountImbalanceArtifact | None,
) -> None:
    prefix = key("a1", source_name, window_name)
    valid = hist[hist["side"].isin([-1, 1])]
    buys = int((valid["side"] == 1).sum())
    sells = int((valid["side"] == -1).sum())
    total = buys + sells
    row[f"{prefix}_count_imbalance"] = np.nan if total == 0 else (buys - sells) / (total + epsilon)
    row[f"{prefix}_count"] = total
    measures = artifact.config.risk_measures if artifact is not None else ("count",)
    for measure in measures:
        buy_value = _side_total(valid, 1, measure)
        sell_value = _side_total(valid, -1, measure)
        weight = _weights_for(artifact, source_name, measure)
        denom = weight.buy_weight * buy_value + weight.sell_weight * sell_value
        value = np.nan if denom <= 0 else (weight.buy_weight * buy_value - weight.sell_weight * sell_value) / (denom + epsilon)
        out_prefix = key("a1", source_name, window_name, measure)
        row[f"{out_prefix}_weighted_imbalance"] = float(value) if np.isfinite(value) else np.nan
        row[f"{out_prefix}_buy_weight"] = weight.buy_weight
        row[f"{out_prefix}_sell_weight"] = weight.sell_weight
        row[f"{out_prefix}_observed_buy"] = buy_value
        row[f"{out_prefix}_observed_sell"] = sell_value


def _training_rows(source: pd.DataFrame, train_end: pd.Timestamp | None) -> pd.DataFrame:
    if source.empty:
        return source.copy()
    valid = source[source["side"].isin([-1, 1])].copy()
    if train_end is None:
        return valid
    return valid[valid["timestamp"] < pd.Timestamp(train_end)].copy()


def _fit_side_weights(source: pd.DataFrame, source_name: str, measure: str, config: CountImbalanceConfig) -> SideWeights:
    buy_total = _side_total(source, 1, measure)
    sell_total = _side_total(source, -1, measure)
    if not np.isfinite(buy_total) or not np.isfinite(sell_total):
        return SideWeights(1.0, 1.0, buy_total, sell_total, source_name, measure, method="missing_measure")
    if config.side_weight_mode != "inverse_market_share" or buy_total <= 0 or sell_total <= 0:
        return SideWeights(1.0, 1.0, buy_total, sell_total, source_name, measure, method="symmetric_fallback")
    total = buy_total + sell_total
    return SideWeights(
        buy_weight=total / (2.0 * buy_total),
        sell_weight=total / (2.0 * sell_total),
        buy_total=buy_total,
        sell_total=sell_total,
        source=source_name,
        measure=measure,
    )


def _weights_for(artifact: CountImbalanceArtifact | None, source_name: str, measure: str) -> SideWeights:
    if artifact is None:
        return SideWeights(1.0, 1.0, np.nan, np.nan, source_name, measure, method="symmetric_default")
    return artifact.weights.get(f"{source_name}:{measure}", SideWeights(1.0, 1.0, np.nan, np.nan, source_name, measure, method="missing_fallback"))


def _side_total(frame: pd.DataFrame, side: int, measure: str) -> float:
    valid = frame[frame["side"] == side]
    if valid.empty:
        return 0.0
    if measure == "count":
        return float(len(valid))
    if measure not in valid.columns:
        return np.nan
    return float(pd.to_numeric(valid[measure], errors="coerce").clip(lower=0.0).sum())
