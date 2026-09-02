"""A4: last-side persistence and switching state."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, interaction, key, last_n, prior
from mechanical_alpha.contracts import AlphaInputBundle

A4_FAST_RFQ_WINDOWS = (5, 10)
A4_SLOW_RFQ_WINDOWS = (25, 50)
A4_FAST_TRADE_WINDOWS = (5, 10)
A4_SLOW_TRADE_WINDOWS = (25, 50)
A4_FUTURE_FLOW_HORIZONS = ("1d", "3d")
A4_MODEL_VERSION = "0.2.0"


@dataclass(frozen=True)
class SidePersistenceConfig:
    """Config local to standalone A4."""

    fast_rfq_windows: tuple[int, ...] = A4_FAST_RFQ_WINDOWS
    slow_rfq_windows: tuple[int, ...] = A4_SLOW_RFQ_WINDOWS
    fast_trade_windows: tuple[int, ...] = A4_FAST_TRADE_WINDOWS
    slow_trade_windows: tuple[int, ...] = A4_SLOW_TRADE_WINDOWS
    future_flow_horizons: tuple[str, ...] = A4_FUTURE_FLOW_HORIZONS
    target_sources: tuple[str, ...] = ("rfq", "trace")
    minimum_fit_observations: int = 10
    regularization_c: float = 1.0
    regularization_alpha: float = 1.0
    slow_refit_frequency: str = "monthly"
    epsilon: float = EPSILON


@dataclass(frozen=True)
class FittedNextSideModel:
    """Frozen logistic or constant next-side model."""

    source: str
    feature_columns: tuple[str, ...]
    coefficients: dict[str, float]
    intercept: float
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    train_observations: int
    positive_rate: float
    model_type: str
    fit_note: str


@dataclass(frozen=True)
class FittedSignedFlowModel:
    """Frozen ridge or constant future signed-CR01-flow model."""

    source: str
    horizon: str
    feature_columns: tuple[str, ...]
    coefficients: dict[str, float]
    intercept: float
    feature_means: dict[str, float]
    feature_scales: dict[str, float]
    train_observations: int
    model_type: str
    fit_note: str


@dataclass(frozen=True)
class SidePersistenceArtifact:
    """Frozen fitted A4 state."""

    config: SidePersistenceConfig
    train_end: pd.Timestamp
    next_side_models: dict[str, FittedNextSideModel]
    signed_flow_models: dict[str, FittedSignedFlowModel]
    model_version: str = A4_MODEL_VERSION


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A4",
        formula="last side persistence states plus train-fitted next-side probability and future signed-CR01 flow models",
        source_fields=("rfqs.side", "rfqs.timestamp", "rfqs.cr01", "events.side", "events.prediction_timestamp", "events.cr01"),
        clock="rfq_event_time | trace_transaction_time",
        window="fast: last 5/10 RFQs or trades; slow: last 25/50 RFQs or trades; future CR01 flow horizons: 1d, 3d",
        min_observations=1,
        missing_policy="NaN when no prior valid-side observations exist; CR01-flow model unavailable when event-level CR01 is absent",
        expected_sign="higher next-side score means higher fitted probability of customer buy; higher signed-flow score means higher expected future customer-buy CR01 flow",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp", "fit uses training rows only", "score uses frozen fitted parameters"),
        computational_cost="O(prediction_rows * window_rows)",
        version=A4_MODEL_VERSION,
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    event_windows: tuple[int, ...] | None = None,
    epsilon: float = EPSILON,
    config: SidePersistenceConfig | None = None,
) -> pd.DataFrame:
    cfg = config or SidePersistenceConfig(epsilon=epsilon)
    if event_windows is None:
        event_windows = tuple(dict.fromkeys(cfg.fast_rfq_windows + cfg.slow_rfq_windows + cfg.fast_trade_windows + cfg.slow_trade_windows))
    context = build_context(bundle)
    return compute_from_context(context, add_features, event_windows=event_windows, epsilon=epsilon)


def config_from_mapping(payload: dict[str, object]) -> SidePersistenceConfig:
    return SidePersistenceConfig(
        fast_rfq_windows=tuple(int(item) for item in payload.get("fast_rfq_windows", A4_FAST_RFQ_WINDOWS)),
        slow_rfq_windows=tuple(int(item) for item in payload.get("slow_rfq_windows", A4_SLOW_RFQ_WINDOWS)),
        fast_trade_windows=tuple(int(item) for item in payload.get("fast_trade_windows", A4_FAST_TRADE_WINDOWS)),
        slow_trade_windows=tuple(int(item) for item in payload.get("slow_trade_windows", A4_SLOW_TRADE_WINDOWS)),
        future_flow_horizons=tuple(str(item) for item in payload.get("future_flow_horizons", A4_FUTURE_FLOW_HORIZONS)),
        target_sources=tuple(str(item) for item in payload.get("target_sources", ("rfq", "trace"))),
        minimum_fit_observations=int(payload.get("minimum_fit_observations", 10)),
        regularization_c=float(payload.get("regularization_c", 1.0)),
        regularization_alpha=float(payload.get("regularization_alpha", 1.0)),
        slow_refit_frequency=str(payload.get("slow_refit_frequency", "monthly")),
        epsilon=float(payload.get("epsilon", EPSILON)),
    )


def fit(
    bundle: AlphaInputBundle,
    *,
    config: SidePersistenceConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> SidePersistenceArtifact:
    """Fit next-side and future signed-CR01-flow models from training rows only."""

    cfg = config or SidePersistenceConfig()
    raw = compute(bundle, config=cfg, epsilon=cfg.epsilon)
    train_end = pd.Timestamp(train_end) if train_end is not None else _default_train_end(raw)
    context = build_context(bundle)
    frame = _attach_targets(raw, context, cfg, target_cutoff=train_end)
    train = frame[frame["prediction_timestamp"] <= train_end].copy()
    feature_columns = _model_feature_columns(train)
    next_side_models = {
        source: _fit_next_side_model(train, source, feature_columns, cfg)
        for source in cfg.target_sources
        if f"target_next_{source}_side_is_buy" in train.columns
    }
    signed_flow_models: dict[str, FittedSignedFlowModel] = {}
    for source in cfg.target_sources:
        for horizon in cfg.future_flow_horizons:
            target = f"target_future_{source}_signed_cr01_flow_{horizon}"
            if target in train.columns:
                signed_flow_models[f"{source}:{horizon}"] = _fit_signed_flow_model(train, source, horizon, target, feature_columns, cfg)
    return SidePersistenceArtifact(cfg, train_end, next_side_models, signed_flow_models)


def score(bundle: AlphaInputBundle, artifact: SidePersistenceArtifact) -> pd.DataFrame:
    """Score A4 fitted models with frozen train-period parameters."""

    raw = compute(bundle, config=artifact.config, epsilon=artifact.config.epsilon)
    _add_model_context_columns(raw)
    for source, model in artifact.next_side_models.items():
        raw[f"a4_fitted_next_{source}_side_buy_probability"] = _predict_probability(raw, model)
        raw[f"a4_fitted_next_{source}_side_model_type"] = model.model_type
        raw[f"a4_fitted_next_{source}_side_fit_note"] = model.fit_note
    for label, model in artifact.signed_flow_models.items():
        source, horizon = label.split(":", maxsplit=1)
        raw[f"a4_fitted_future_{source}_signed_cr01_flow_{horizon}_score"] = _predict_linear(raw, model)
        raw[f"a4_fitted_future_{source}_signed_cr01_flow_{horizon}_model_type"] = model.model_type
        raw[f"a4_fitted_future_{source}_signed_cr01_flow_{horizon}_fit_note"] = model.fit_note
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
) -> None:
    for source_name, source in {"rfq": context.rfqs, "trace": context.traces}.items():
        valid = prior(source[source["side"].isin([-1, 1])], bond_id, asof)
        if valid.empty:
            row[f"a4_{source_name}_last_side"] = np.nan
            row[f"a4_{source_name}_same_side_run_length"] = np.nan
            row[f"a4_{source_name}_elapsed_seconds_since_side_change"] = np.nan
        else:
            last_side = int(valid.iloc[-1]["side"])
            row[f"a4_{source_name}_last_side"] = last_side
            row[f"a4_{source_name}_same_side_run_length"] = _same_side_run_length(valid["side"].tolist())
            row[f"a4_{source_name}_elapsed_seconds_since_side_change"] = _elapsed_since_side_change(valid, asof)
        for window in event_windows:
            hist = last_n(valid, int(window))
            prefix = key("a4", source_name, f"last_{window}")
            row[f"{prefix}_fraction_same_as_last"] = _fraction_same_as_last(hist)
            row[f"{prefix}_switching_hazard"] = _switching_hazard(hist, epsilon)
            row[f"{prefix}_signed_cr01_imbalance"] = _signed_cr01_imbalance(hist, epsilon)
            imbalance_source = "trace_side_valid" if source_name == "trace" else "rfq_all_inquiries"
            imbalance = row.get(f"a1_{imbalance_source}_last_{window}_count_imbalance")
            notional = row.get(f"a2_{imbalance_source}_last_{window}_raw_notional_imbalance")
            last_side = row.get(f"a4_{source_name}_last_side")
            row[f"{prefix}_last_side_x_count_imbalance"] = interaction(last_side, imbalance)
            row[f"{prefix}_last_side_x_notional_imbalance"] = interaction(last_side, notional)


def _same_side_run_length(sides: list[float]) -> int:
    if not sides:
        return 0
    last = sides[-1]
    count = 0
    for side in reversed(sides):
        if side != last:
            break
        count += 1
    return count


def _elapsed_since_side_change(valid: pd.DataFrame, asof: pd.Timestamp) -> float:
    if len(valid) < 2:
        return np.nan
    last_side = valid.iloc[-1]["side"]
    changed = valid[valid["side"] != last_side]
    if changed.empty:
        return np.nan
    return float((asof - pd.Timestamp(changed.iloc[-1]["timestamp"])).total_seconds())


def _fraction_same_as_last(frame: pd.DataFrame) -> float:
    if frame.empty:
        return np.nan
    last_side = frame.iloc[-1]["side"]
    return float((frame["side"] == last_side).mean())


def _switching_hazard(frame: pd.DataFrame, epsilon: float) -> float:
    if len(frame) < 2:
        return np.nan
    sides = frame["side"].to_numpy(dtype=float)
    switches = float(np.sum(sides[1:] != sides[:-1]))
    return switches / (len(sides) - 1 + epsilon)


def _signed_cr01_imbalance(frame: pd.DataFrame, epsilon: float) -> float:
    if frame.empty or "cr01" not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame["cr01"], errors="coerce")
    sides = pd.to_numeric(frame["side"], errors="coerce")
    mask = values.notna() & sides.isin([-1, 1])
    if not mask.any():
        return np.nan
    gross = values[mask].abs().sum()
    signed = (sides[mask] * values[mask].abs()).sum()
    return float(signed / (gross + epsilon))


def _default_train_end(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty:
        return pd.Timestamp.min
    times = pd.Series(pd.to_datetime(frame["prediction_timestamp"]).sort_values().unique())
    idx = max(0, min(len(times) - 1, int(np.floor((len(times) - 1) * 0.70))))
    return pd.Timestamp(times.iloc[idx])


def _attach_targets(
    raw: pd.DataFrame,
    context: AlphaContext,
    config: SidePersistenceConfig,
    *,
    target_cutoff: pd.Timestamp | None = None,
) -> pd.DataFrame:
    frame = raw.copy()
    cutoff = pd.Timestamp(target_cutoff) if target_cutoff is not None else None
    for source_name, source in {"rfq": context.rfqs, "trace": context.traces}.items():
        if source_name not in config.target_sources or source.empty:
            continue
        valid = source[source["side"].isin([-1, 1])].sort_values(["bond_id", "timestamp"]).copy()
        if valid.empty:
            continue
        frame[f"target_next_{source_name}_side_is_buy"] = [
            _next_side_is_buy(valid, str(row.bond_id), pd.Timestamp(row.prediction_timestamp), cutoff=cutoff)
            for row in frame.itertuples(index=False)
        ]
        if "cr01" in valid.columns:
            for horizon in config.future_flow_horizons:
                frame[f"target_future_{source_name}_signed_cr01_flow_{horizon}"] = [
                    _future_signed_cr01_flow(
                        valid,
                        str(row.bond_id),
                        pd.Timestamp(row.prediction_timestamp),
                        _to_timedelta(horizon),
                        cutoff=cutoff,
                    )
                    for row in frame.itertuples(index=False)
                ]
    _add_model_context_columns(frame)
    return frame


def _add_model_context_columns(frame: pd.DataFrame) -> None:
    timestamps = pd.to_datetime(frame["prediction_timestamp"])
    frame["a4_hour"] = timestamps.dt.hour.astype(float)
    frame["a4_weekday"] = timestamps.dt.weekday.astype(float)


def _next_side_is_buy(
    frame: pd.DataFrame,
    bond_id: str,
    asof: pd.Timestamp,
    *,
    cutoff: pd.Timestamp | None = None,
) -> float:
    future = frame[(frame["bond_id"].astype(str) == bond_id) & (frame["timestamp"] > asof)]
    if cutoff is not None:
        future = future[future["timestamp"] <= cutoff]
    if future.empty:
        return np.nan
    return 1.0 if int(future.iloc[0]["side"]) == 1 else 0.0


def _future_signed_cr01_flow(
    frame: pd.DataFrame,
    bond_id: str,
    asof: pd.Timestamp,
    horizon: pd.Timedelta,
    *,
    cutoff: pd.Timestamp | None = None,
) -> float:
    end = asof + horizon
    if cutoff is not None:
        end = min(end, cutoff)
    if end <= asof:
        return np.nan
    future = frame[(frame["bond_id"].astype(str) == bond_id) & (frame["timestamp"] > asof) & (frame["timestamp"] <= end)]
    if future.empty or "cr01" not in future.columns:
        return np.nan
    values = pd.to_numeric(future["cr01"], errors="coerce")
    sides = pd.to_numeric(future["side"], errors="coerce")
    mask = values.notna() & sides.isin([-1, 1])
    if not mask.any():
        return np.nan
    return float((sides[mask] * values[mask].abs()).sum())


def _model_feature_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    columns = [
        column
        for column in frame.columns
        if (
            column.startswith("a4_")
            and not column.startswith("a4_fitted_")
            and pd.api.types.is_numeric_dtype(frame[column])
        )
    ]
    return tuple(column for column in columns if not column.startswith("a4_latest_"))


def _fit_next_side_model(
    frame: pd.DataFrame,
    source: str,
    feature_columns: tuple[str, ...],
    config: SidePersistenceConfig,
) -> FittedNextSideModel:
    target = f"target_next_{source}_side_is_buy"
    work = frame[[*feature_columns, target]].replace([np.inf, -np.inf], np.nan)
    clean = work[work[target].notna()].copy()
    if clean.empty:
        return FittedNextSideModel(source, (), {}, np.nan, {}, {}, 0, np.nan, "constant_fallback", "no_training_observations")
    usable = tuple(column for column in feature_columns if clean[column].notna().any())
    y = clean[target].astype(int)
    positive_rate = float(y.mean())
    if len(clean) < config.minimum_fit_observations or y.nunique() < 2 or not usable:
        return FittedNextSideModel(
            source,
            (),
            {},
            _logit(positive_rate),
            {},
            {},
            int(len(clean)),
            positive_rate,
            "constant_fallback",
            "insufficient_or_single_class_training_observations",
        )
    x = clean[list(usable)].astype(float)
    means = x.mean().to_dict()
    scales = x.std(ddof=0).replace(0.0, 1.0).fillna(1.0).to_dict()
    scaled = (x.fillna(pd.Series(means)) - pd.Series(means)) / pd.Series(scales)
    model = LogisticRegression(C=config.regularization_c, solver="lbfgs", max_iter=1_000, random_state=0)
    fitted = model.fit(scaled, y)
    coefficients = {column: float(value) for column, value in zip(usable, fitted.coef_[0], strict=True)}
    return FittedNextSideModel(
        source,
        usable,
        coefficients,
        float(fitted.intercept_[0]),
        {str(k): float(v) for k, v in means.items()},
        {str(k): float(v) for k, v in scales.items()},
        int(len(clean)),
        positive_rate,
        "logistic_regression",
        "train_only_logistic_fit",
    )


def _fit_signed_flow_model(
    frame: pd.DataFrame,
    source: str,
    horizon: str,
    target: str,
    feature_columns: tuple[str, ...],
    config: SidePersistenceConfig,
) -> FittedSignedFlowModel:
    work = frame[[*feature_columns, target]].replace([np.inf, -np.inf], np.nan)
    clean = work[work[target].notna()].copy()
    usable = tuple(column for column in feature_columns if not clean.empty and clean[column].notna().any())
    if len(clean) < config.minimum_fit_observations or not usable:
        mean = float(clean[target].mean()) if len(clean) else np.nan
        return FittedSignedFlowModel(source, horizon, (), {}, mean, {}, {}, int(len(clean)), "constant_fallback", "insufficient_training_observations")
    x = clean[list(usable)].astype(float)
    y = clean[target].astype(float)
    means = x.mean().to_dict()
    scales = x.std(ddof=0).replace(0.0, 1.0).fillna(1.0).to_dict()
    scaled = (x.fillna(pd.Series(means)) - pd.Series(means)) / pd.Series(scales)
    fitted = Ridge(alpha=config.regularization_alpha).fit(scaled, y)
    coefficients = {column: float(value) for column, value in zip(usable, fitted.coef_, strict=True)}
    return FittedSignedFlowModel(
        source,
        horizon,
        usable,
        coefficients,
        float(fitted.intercept_),
        {str(k): float(v) for k, v in means.items()},
        {str(k): float(v) for k, v in scales.items()},
        int(len(clean)),
        "ridge",
        "train_only_ridge_fit",
    )


def _predict_probability(frame: pd.DataFrame, model: FittedNextSideModel) -> np.ndarray:
    if not model.feature_columns:
        return _sigmoid(np.full(len(frame), model.intercept, dtype=float))
    linear = _linear_score(frame, model.feature_columns, model.feature_means, model.feature_scales, model.coefficients, model.intercept)
    return _sigmoid(linear)


def _predict_linear(frame: pd.DataFrame, model: FittedSignedFlowModel) -> np.ndarray:
    if not model.feature_columns:
        return np.full(len(frame), model.intercept, dtype=float)
    return _linear_score(frame, model.feature_columns, model.feature_means, model.feature_scales, model.coefficients, model.intercept)


def _linear_score(
    frame: pd.DataFrame,
    feature_columns: tuple[str, ...],
    means: dict[str, float],
    scales: dict[str, float],
    coefficients: dict[str, float],
    intercept: float,
) -> np.ndarray:
    x = frame[list(feature_columns)].replace([np.inf, -np.inf], np.nan)
    x = x.fillna(pd.Series(means))
    scaled = (x - pd.Series(means)) / pd.Series(scales)
    coefs = np.asarray([coefficients[column] for column in feature_columns], dtype=float)
    return np.asarray(intercept + scaled.to_numpy(dtype=float) @ coefs, dtype=float)


def _logit(value: float) -> float:
    clipped = float(np.clip(value, EPSILON, 1.0 - EPSILON))
    return float(np.log(clipped / (1.0 - clipped)))


def _sigmoid(value: float | np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-np.clip(value, -40.0, 40.0))), dtype=float)


def _to_timedelta(window: str) -> pd.Timedelta:
    text = str(window).strip().lower()
    if text.endswith("d") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="D")
    if text.endswith("h") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="h")
    if text.endswith("m") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="m")
    return pd.Timedelta(text)
