"""A2: RFQ and TRACE notional imbalance."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_CALENDAR_WINDOWS, DEFAULT_EVENT_WINDOWS, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, filter_event_kind, filter_firm_inquiries, key, last_n, prior, transform_notional, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle


@dataclass(frozen=True)
class RiskImbalanceConfig:
    """Configuration for fitted asymmetric notional and CR01 imbalance."""

    event_windows: tuple[int, ...] = DEFAULT_EVENT_WINDOWS
    calendar_windows: tuple[str, ...] = DEFAULT_CALENDAR_WINDOWS
    risk_measures: tuple[str, ...] = ("cr01", "notional")
    variants: tuple[str, ...] = ("raw", "log", "capped", "sqrt")
    side_weight_mode: str = "inverse_market_share"
    epsilon: float = EPSILON


@dataclass(frozen=True)
class RiskSideWeights:
    """Frozen buy/sell weights for one source, measure, and transform."""

    buy_weight: float
    sell_weight: float
    buy_total: float
    sell_total: float
    source: str
    measure: str
    variant: str
    method: str = "inverse_market_share"


@dataclass(frozen=True)
class RiskImbalanceArtifact:
    """Train-fitted A2 side weights."""

    config: RiskImbalanceConfig
    weights: dict[str, RiskSideWeights] = field(default_factory=dict)


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A2",
        formula="sum(w_side * side_j * transformed_risk_j) / (sum(w_side * abs(transformed_risk_j)) + epsilon), with CR01 preferred",
        source_fields=("rfqs.side", "rfqs.size", "rfqs.cr01", "events.side", "events.notional", "events.cr01"),
        clock="calendar_time | rfq_event_time | trace_transaction_time",
        window="configurable event and calendar windows",
        min_observations=1,
        missing_policy="NaN when side or requested risk measure is unavailable; CR01 is not replaced with notional unless explicitly scored as notional",
        expected_sign="positive means larger recent customer-buy traded credit risk after adjusting for market side drift",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp", "side weights and transform caps fitted on training rows only"),
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
    config: RiskImbalanceConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> RiskImbalanceArtifact:
    """Fit asymmetric side weights from training rows only."""

    cfg = config or RiskImbalanceConfig()
    context = build_context(bundle)
    weights: dict[str, RiskSideWeights] = {}
    for source_name, source in _sources(context).items():
        training = _training_rows(source, train_end)
        for measure in cfg.risk_measures:
            for variant in cfg.variants:
                fitted = _fit_side_weights(training, source_name, measure, variant, cfg)
                weights[f"{source_name}:{measure}:{variant}"] = fitted
    return RiskImbalanceArtifact(config=cfg, weights=weights)


def score(bundle: AlphaInputBundle, artifact: RiskImbalanceArtifact) -> pd.DataFrame:
    """Score A2 with frozen train-fitted side weights."""

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
    artifact: RiskImbalanceArtifact | None = None,
) -> None:
    sources = _sources(context)
    for source_name, source in sources.items():
        for window in event_windows:
            hist = last_n(prior(source, bond_id, asof), int(window))
            _write_notional(row, source_name, f"last_{window}", hist, epsilon, artifact)
        for window in calendar_windows:
            hist = within_timedelta(prior(source, bond_id, asof), asof, pd.Timedelta(str(window)))
            _write_notional(row, source_name, str(window), hist, epsilon, artifact)


def _sources(context: AlphaContext) -> dict[str, pd.DataFrame]:
    return {
        "rfq_all_inquiries": context.rfqs,
        "rfq_firm_inquiries": filter_firm_inquiries(context.rfqs),
        "rfq_firm_ups": filter_event_kind(context.rfqs, ("firm_up", "firm-up", "firmup")),
        "rfq_executions": filter_event_kind(context.rfqs, ("execution", "executed")),
        "trace_side_valid": context.traces[context.traces["side"].isin([-1, 1])],
    }


def _write_notional(
    row: dict[str, object],
    source_name: str,
    window_name: str,
    hist: pd.DataFrame,
    epsilon: float,
    artifact: RiskImbalanceArtifact | None,
) -> None:
    valid = hist[hist["side"].isin([-1, 1])]
    for variant in ("raw", "log", "capped", "sqrt"):
        transformed = transform_notional(valid["notional"], variant)
        denominator = float(np.nansum(np.abs(transformed)))
        value = np.nan
        if denominator > 0:
            value = float(np.nansum(valid["side"].to_numpy(dtype=float) * transformed) / (denominator + epsilon))
        row[f"{key('a2', source_name, window_name)}_{variant}_notional_imbalance"] = value
    if artifact is None:
        return
    for measure in artifact.config.risk_measures:
        for variant in artifact.config.variants:
            transformed = _transform_measure(valid, measure, variant)
            if transformed is None:
                value = np.nan
                weighted_denominator = np.nan
                buy_observed = np.nan
                sell_observed = np.nan
            else:
                weights = _weights_for(artifact, source_name, measure, variant)
                sides = valid["side"].to_numpy(dtype=float)
                side_weights = np.where(sides == 1, weights.buy_weight, weights.sell_weight)
                weighted_denominator = float(np.nansum(side_weights * np.abs(transformed)))
                value = np.nan
                if weighted_denominator > 0:
                    value = float(np.nansum(side_weights * sides * transformed) / (weighted_denominator + epsilon))
                buy_observed = float(np.nansum(transformed[sides == 1]))
                sell_observed = float(np.nansum(transformed[sides == -1]))
            prefix = key("a2", source_name, window_name, measure, variant)
            weights = _weights_for(artifact, source_name, measure, variant)
            row[f"{prefix}_imbalance"] = value if np.isfinite(value) else np.nan
            row[f"{prefix}_weighted_denominator"] = weighted_denominator
            row[f"{prefix}_buy_weight"] = weights.buy_weight
            row[f"{prefix}_sell_weight"] = weights.sell_weight
            row[f"{prefix}_observed_buy"] = buy_observed
            row[f"{prefix}_observed_sell"] = sell_observed


def _training_rows(source: pd.DataFrame, train_end: pd.Timestamp | None) -> pd.DataFrame:
    if source.empty:
        return source.copy()
    valid = source[source["side"].isin([-1, 1])].copy()
    if train_end is None:
        return valid
    return valid[valid["timestamp"] < pd.Timestamp(train_end)].copy()


def _fit_side_weights(source: pd.DataFrame, source_name: str, measure: str, variant: str, config: RiskImbalanceConfig) -> RiskSideWeights:
    transformed = _transform_measure(source, measure, variant)
    if transformed is None or source.empty:
        return RiskSideWeights(1.0, 1.0, np.nan, np.nan, source_name, measure, variant, method="missing_measure")
    sides = source["side"].to_numpy(dtype=float)
    buy_total = float(np.nansum(transformed[sides == 1]))
    sell_total = float(np.nansum(transformed[sides == -1]))
    if config.side_weight_mode != "inverse_market_share" or buy_total <= 0 or sell_total <= 0:
        return RiskSideWeights(1.0, 1.0, buy_total, sell_total, source_name, measure, variant, method="symmetric_fallback")
    total = buy_total + sell_total
    return RiskSideWeights(
        buy_weight=total / (2.0 * buy_total),
        sell_weight=total / (2.0 * sell_total),
        buy_total=buy_total,
        sell_total=sell_total,
        source=source_name,
        measure=measure,
        variant=variant,
    )


def _weights_for(artifact: RiskImbalanceArtifact, source_name: str, measure: str, variant: str) -> RiskSideWeights:
    return artifact.weights.get(
        f"{source_name}:{measure}:{variant}",
        RiskSideWeights(1.0, 1.0, np.nan, np.nan, source_name, measure, variant, method="missing_fallback"),
    )


def _transform_measure(frame: pd.DataFrame, measure: str, variant: str) -> np.ndarray | None:
    if measure not in frame.columns:
        return None
    values = pd.to_numeric(frame[measure], errors="coerce").clip(lower=0.0)
    return transform_notional(values, variant)
