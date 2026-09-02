"""A16: RFQ scarcity and disagreement."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, first_existing_value, last_n, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle

A16_FAST_CALENDAR_WINDOWS = ("1d", "3d")
A16_SLOW_CALENDAR_WINDOWS = ("5d", "10d", "20d", "40d", "60d", "120d")
A16_FAST_RFQ_WINDOWS = (5, 10)
A16_SLOW_RFQ_WINDOWS = (25, 50)
A16_MODEL_VERSION = "0.2.0"
A16_DEFAULT_TARGETS = ("executed", "firmed_up", "responded")


@dataclass(frozen=True)
class RFQScarcityConfig:
    """Config local to standalone A16."""

    fast_calendar_windows: tuple[str, ...] = A16_FAST_CALENDAR_WINDOWS
    slow_calendar_windows: tuple[str, ...] = A16_SLOW_CALENDAR_WINDOWS
    fast_rfq_windows: tuple[int, ...] = A16_FAST_RFQ_WINDOWS
    slow_rfq_windows: tuple[int, ...] = A16_SLOW_RFQ_WINDOWS
    target_columns: tuple[str, ...] = A16_DEFAULT_TARGETS
    minimum_fit_observations: int = 10
    regularization_c: float = 1.0
    slow_refit_frequency: str = "monthly"
    epsilon: float = EPSILON


@dataclass(frozen=True)
class FittedRFQQualityModel:
    """Frozen logistic or fallback model for one RFQ quality target."""

    target: str
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
class RFQScarcityArtifact:
    """Frozen A16 fitted liquidity-quality state."""

    config: RFQScarcityConfig
    train_end: pd.Timestamp
    models: dict[str, FittedRFQQualityModel]
    model_version: str = A16_MODEL_VERSION


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
        target_columns=tuple(str(item) for item in payload.get("target_columns", A16_DEFAULT_TARGETS)),
        minimum_fit_observations=int(payload.get("minimum_fit_observations", 10)),
        regularization_c=float(payload.get("regularization_c", 1.0)),
        slow_refit_frequency=str(payload.get("slow_refit_frequency", "monthly")),
        epsilon=float(payload.get("epsilon", EPSILON)),
    )


def fit(
    bundle: AlphaInputBundle,
    *,
    config: RFQScarcityConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> RFQScarcityArtifact:
    """Fit simple RFQ quality probabilities on training rows only."""

    cfg = config or RFQScarcityConfig()
    raw = compute(bundle, config=cfg)
    train_end = pd.Timestamp(train_end) if train_end is not None else _default_train_end(raw)
    frame = _attach_rfq_targets(raw, bundle.rfqs, cfg.target_columns)
    train = frame[frame["prediction_timestamp"] <= train_end].copy()
    feature_columns = _model_feature_columns(train)
    models = {
        target: _fit_logistic_target(train, target, feature_columns, cfg)
        for target in cfg.target_columns
        if target in train.columns
    }
    return RFQScarcityArtifact(config=cfg, train_end=train_end, models=models)


def score(bundle: AlphaInputBundle, artifact: RFQScarcityArtifact) -> pd.DataFrame:
    """Score frozen A16 fitted RFQ quality models without refitting."""

    raw = compute(bundle, config=artifact.config)
    for target, model in artifact.models.items():
        raw[f"a16_fitted_probability_{target}"] = _predict_probability(raw, model)
        raw[f"a16_fitted_probability_{target}_model_type"] = model.model_type
        raw[f"a16_fitted_probability_{target}_fit_note"] = model.fit_note
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


def _default_train_end(frame: pd.DataFrame) -> pd.Timestamp:
    if frame.empty:
        return pd.Timestamp.min
    times = pd.Series(pd.to_datetime(frame["prediction_timestamp"]).sort_values().unique())
    idx = max(0, min(len(times) - 1, int(np.floor((len(times) - 1) * 0.70))))
    return pd.Timestamp(times.iloc[idx])


def _attach_rfq_targets(raw: pd.DataFrame, rfqs: pd.DataFrame | None, targets: tuple[str, ...]) -> pd.DataFrame:
    if rfqs is None or rfqs.empty:
        return raw.copy()
    available = [target for target in targets if target in rfqs.columns]
    if not available:
        return raw.copy()
    target_frame = rfqs.copy()
    target_frame["prediction_timestamp"] = pd.to_datetime(target_frame["timestamp"], utc=False)
    target_frame["bond_id"] = target_frame["bond_id"].astype(str)
    return raw.merge(target_frame[["prediction_timestamp", "bond_id", *available]], on=["prediction_timestamp", "bond_id"], how="left")


def _model_feature_columns(frame: pd.DataFrame) -> tuple[str, ...]:
    columns = [
        column
        for column in frame.columns
        if column.startswith("a16_")
        and (
            column.endswith("_rate")
            or column.endswith("_mean_response_count")
            or column.endswith("_mean_quote_dispersion")
            or column.endswith("_mean_latency_ms")
            or column in {
                "a16_latest_response_count",
                "a16_latest_response_scarcity",
                "a16_latest_dealer_count",
                "a16_latest_quote_dispersion",
                "a16_latest_response_latency_ms",
                "a16_latest_executable_indication_age_seconds",
            }
        )
    ]
    return tuple(column for column in columns if pd.api.types.is_numeric_dtype(frame[column]))


def _fit_logistic_target(
    frame: pd.DataFrame,
    target: str,
    feature_columns: tuple[str, ...],
    config: RFQScarcityConfig,
) -> FittedRFQQualityModel:
    work = frame[[*feature_columns, target]].replace([np.inf, -np.inf], np.nan)
    clean = work[work[target].notna()].copy()
    if clean.empty:
        return FittedRFQQualityModel(target, (), {}, np.nan, {}, {}, 0, np.nan, "constant_fallback", "no_training_observations")
    usable_columns = tuple(column for column in feature_columns if clean[column].notna().any())
    y = clean[target].astype(bool).astype(int)
    positive_rate = float(y.mean())
    if len(clean) < config.minimum_fit_observations or y.nunique() < 2 or not usable_columns:
        return FittedRFQQualityModel(
            target,
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
    x = clean[list(usable_columns)].astype(float)
    means = x.mean().to_dict()
    scales = x.std(ddof=0).replace(0.0, 1.0).fillna(1.0).to_dict()
    x_scaled = (x.fillna(pd.Series(means)) - pd.Series(means)) / pd.Series(scales)
    model = LogisticRegression(C=config.regularization_c, solver="lbfgs", max_iter=1_000, random_state=0)
    fitted = model.fit(x_scaled, y)
    coefficients = {column: float(value) for column, value in zip(usable_columns, fitted.coef_[0], strict=True)}
    return FittedRFQQualityModel(
        target=target,
        feature_columns=usable_columns,
        coefficients=coefficients,
        intercept=float(fitted.intercept_[0]),
        feature_means={str(k): float(v) for k, v in means.items()},
        feature_scales={str(k): float(v) for k, v in scales.items()},
        train_observations=int(len(clean)),
        positive_rate=positive_rate,
        model_type="logistic_regression",
        fit_note="train_only_logistic_fit",
    )


def _predict_probability(frame: pd.DataFrame, model: FittedRFQQualityModel) -> np.ndarray:
    if not model.feature_columns:
        return np.full(len(frame), _sigmoid(model.intercept), dtype=float)
    x = frame[list(model.feature_columns)].replace([np.inf, -np.inf], np.nan)
    x = x.fillna(pd.Series(model.feature_means))
    scaled = (x - pd.Series(model.feature_means)) / pd.Series(model.feature_scales)
    coefs = np.asarray([model.coefficients[column] for column in model.feature_columns], dtype=float)
    return _sigmoid(model.intercept + scaled.to_numpy(dtype=float) @ coefs)


def _logit(value: float) -> float:
    clipped = float(np.clip(value, EPSILON, 1.0 - EPSILON))
    return float(np.log(clipped / (1.0 - clipped)))


def _sigmoid(value: float | np.ndarray) -> np.ndarray:
    return np.asarray(1.0 / (1.0 + np.exp(-np.clip(value, -40.0, 40.0))), dtype=float)
