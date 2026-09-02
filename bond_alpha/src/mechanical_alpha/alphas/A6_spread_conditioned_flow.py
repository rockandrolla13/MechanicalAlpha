"""A6: spread-conditioned flow pressure."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet, Ridge

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
A6_DEFAULT_TARGETS = ("future_clean_price_move", "future_issuer_residual_move")


@dataclass(frozen=True)
class SpreadConditionedFlowConfig:
    """Config local to standalone A6."""

    fast_calendar_windows: tuple[str, ...] = A6_FAST_CALENDAR_WINDOWS
    slow_calendar_windows: tuple[str, ...] = A6_SLOW_CALENDAR_WINDOWS
    fast_trade_windows: tuple[int, ...] = A6_FAST_TRADE_WINDOWS
    slow_trade_windows: tuple[int, ...] = A6_SLOW_TRADE_WINDOWS
    flow_measures: tuple[str, ...] = ("notional", "cr01")
    target_columns: tuple[str, ...] = A6_DEFAULT_TARGETS
    model_type: str = "ridge"
    minimum_fit_observations: int = 10
    regularization_alpha: float = 1.0
    slow_refit_frequency: str = "monthly"
    epsilon: float = EPSILON


@dataclass(frozen=True)
class FittedSpreadFlowModel:
    """Frozen linear model for one A6 target."""

    target: str
    feature_columns: tuple[str, ...]
    coefficients: dict[str, float]
    intercept: float
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    train_observations: int
    model_type: str
    fit_note: str


@dataclass(frozen=True)
class SpreadConditionedFlowArtifact:
    """Frozen A6 raw-feature model state."""

    config: SpreadConditionedFlowConfig
    train_end: pd.Timestamp
    models: dict[str, FittedSpreadFlowModel]
    model_version: str = A6_MODEL_VERSION


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
        target_columns=tuple(str(item) for item in payload.get("target_columns", A6_DEFAULT_TARGETS)),
        model_type=str(payload.get("model_type", "ridge")),
        minimum_fit_observations=int(payload.get("minimum_fit_observations", 10)),
        regularization_alpha=float(payload.get("regularization_alpha", 1.0)),
        slow_refit_frequency=str(payload.get("slow_refit_frequency", "monthly")),
        epsilon=float(payload.get("epsilon", EPSILON)),
    )


def fit(
    bundle: AlphaInputBundle,
    *,
    config: SpreadConditionedFlowConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> SpreadConditionedFlowArtifact:
    """Fit transparent linear A6 target models on training rows only."""

    cfg = config or SpreadConditionedFlowConfig()
    raw = compute(bundle, config=cfg)
    train_end = pd.Timestamp(train_end) if train_end is not None else _default_train_end(raw)
    frame = _attach_event_targets(raw, bundle.events, cfg.target_columns)
    train = frame[frame["prediction_timestamp"] <= train_end].copy()
    feature_columns = _model_feature_columns(train)
    models = {
        target: _fit_linear_target(train, target, feature_columns, cfg)
        for target in cfg.target_columns
        if target in train.columns
    }
    return SpreadConditionedFlowArtifact(config=cfg, train_end=train_end, models=models)


def score(bundle: AlphaInputBundle, artifact: SpreadConditionedFlowArtifact) -> pd.DataFrame:
    """Score frozen A6 fitted models without refitting."""

    raw = compute(bundle, config=artifact.config)
    for target, model in artifact.models.items():
        raw[f"a6_fitted_{target}_score"] = _predict_linear(raw, model)
        raw[f"a6_fitted_{target}_model_type"] = model.model_type
        raw[f"a6_fitted_{target}_fit_note"] = model.fit_note
    return raw


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


def _default_train_end(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty:
        return pd.Timestamp.min
    times = pd.Series(pd.to_datetime(frame["prediction_timestamp"]).sort_values().unique())
    idx = max(0, min(len(times) - 1, int(np.floor((len(times) - 1) * 0.70))))
    return pd.Timestamp(times.iloc[idx])


def _attach_event_targets(raw: pd.DataFrame, events: pd.DataFrame, targets: tuple[str, ...]) -> pd.DataFrame:
    if events.empty:
        return raw.copy()
    available = [target for target in targets if target in events.columns]
    if not available:
        return raw.copy()
    target_frame = events.copy()
    target_frame["prediction_timestamp"] = pd.to_datetime(target_frame["prediction_timestamp"], utc=False)
    target_frame["bond_id"] = target_frame["bond_id"].astype(str)
    return raw.merge(target_frame[["prediction_timestamp", "bond_id", *available]], on=["prediction_timestamp", "bond_id"], how="left")


def _model_feature_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    columns = [
        column
        for column in frame.columns
        if column.startswith("a6_")
        and (
            column.endswith("_flow_pressure")
            or column.endswith("_flow_x_spread")
            or column.endswith("_flow_x_spread_percentile")
            or column.endswith("_flow_x_composite_staleness")
            or column in {"a6_latest_composite_spread", "a6_latest_spread_percentile", "a6_latest_composite_staleness_seconds"}
        )
    ]
    return tuple(column for column in columns if pd.api.types.is_numeric_dtype(frame[column]))


def _fit_linear_target(
    frame: pd.DataFrame,
    target: str,
    feature_columns: tuple[str, ...],
    config: SpreadConditionedFlowConfig,
) -> FittedSpreadFlowModel:
    work = frame[[*feature_columns, target]].replace([np.inf, -np.inf], np.nan)
    clean = work[work[target].notna()].copy()
    usable_columns = tuple(column for column in feature_columns if clean[column].notna().any())
    if len(clean) < config.minimum_fit_observations or not usable_columns:
        mean = float(clean[target].mean()) if len(clean) else np.nan
        return FittedSpreadFlowModel(target, (), {}, mean, {}, {}, int(len(clean)), "constant_fallback", "insufficient_training_observations")
    x = clean[list(usable_columns)].astype(float)
    y = clean[target].astype(float)
    means = x.mean().to_dict()
    scales = x.std(ddof=0).replace(0.0, 1.0).fillna(1.0).to_dict()
    x_scaled = (x.fillna(pd.Series(means)) - pd.Series(means)) / pd.Series(scales)
    if config.model_type == "elastic_net":
        model = ElasticNet(alpha=config.regularization_alpha, l1_ratio=0.25, random_state=0, max_iter=10_000)
    else:
        model = Ridge(alpha=config.regularization_alpha)
    fitted = model.fit(x_scaled, y)
    coefficients = {column: float(value) for column, value in zip(usable_columns, fitted.coef_, strict=True)}
    return FittedSpreadFlowModel(
        target=target,
        feature_columns=usable_columns,
        coefficients=coefficients,
        intercept=float(fitted.intercept_),
        feature_means={str(k): float(v) for k, v in means.items()},
        feature_scales={str(k): float(v) for k, v in scales.items()},
        train_observations=int(len(clean)),
        model_type=config.model_type,
        fit_note="train_only_linear_fit",
    )


def _predict_linear(frame: pd.DataFrame, model: FittedSpreadFlowModel) -> np.ndarray:
    if not model.feature_columns:
        return np.full(len(frame), model.intercept, dtype=float)
    x = frame[list(model.feature_columns)].replace([np.inf, -np.inf], np.nan)
    x = x.fillna(pd.Series(model.feature_means))
    scaled = (x - pd.Series(model.feature_means)) / pd.Series(model.feature_scales)
    coefs = np.asarray([model.coefficients[column] for column in model.feature_columns], dtype=float)
    return np.asarray(model.intercept + scaled.to_numpy(dtype=float) @ coefs, dtype=float)
