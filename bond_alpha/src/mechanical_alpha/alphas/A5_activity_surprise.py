"""A5: fitted multi-clock activity surprise.

This standalone alpha fits normal activity from training-period population
history and scores point-in-time deviations from the frozen baseline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd
import statsmodels.api as sm

from mechanical_alpha.alpha_common import EPSILON, FeatureDefinition, build_context
from mechanical_alpha.alpha_common.context import AlphaContext, filter_event_kind, key, last_n, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle

A5_FAST_CALENDAR_WINDOWS = ("1d", "3d")
A5_SLOW_CALENDAR_WINDOWS = ("5d", "10d", "20d", "40d", "60d", "120d")
A5_CALENDAR_WINDOWS = A5_FAST_CALENDAR_WINDOWS + A5_SLOW_CALENDAR_WINDOWS
A5_RFQ_EVENT_WINDOWS = (5, 10, 25, 50)
A5_TRADE_EVENT_WINDOWS = (5, 10, 25, 50)
A5_MODEL_VERSION = "0.3.0"

_MEASURES = ("notional", "signed_notional", "gross_dv01", "signed_dv01", "gross_cr01", "signed_cr01")


@dataclass(frozen=True)
class ActivitySurpriseConfig:
    """External A5 configuration kept local to the standalone alpha."""

    calendar_windows: tuple[str, ...] = A5_CALENDAR_WINDOWS
    rfq_event_windows: tuple[int, ...] = A5_RFQ_EVENT_WINDOWS
    trade_event_windows: tuple[int, ...] = A5_TRADE_EVENT_WINDOWS
    event_types: tuple[str, ...] = ("inquiry", "firmup", "execution", "trace_trade")
    model_type: str = "auto"
    pooling_levels: tuple[str, ...] = ("bond", "issuer", "liquidity", "rating_sector_maturity", "global")
    minimum_observations: int = 3
    epsilon: float = EPSILON
    winsorization: float = 0.99
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    selection_metric: str = "validation_standardized_error"
    selected_calendar_windows: tuple[str, ...] = A5_CALENDAR_WINDOWS
    selected_rfq_event_windows: tuple[int, ...] = A5_RFQ_EVENT_WINDOWS
    selected_trade_event_windows: tuple[int, ...] = A5_TRADE_EVENT_WINDOWS
    frozen_after_fit: bool = True
    slow_refit_frequency: str = "monthly"
    allow_static_bond_dv01_fallback: bool = False
    allow_static_bond_cr01_fallback: bool = False
    static_risk_unit: str | None = None


@dataclass(frozen=True)
class BaselineKey:
    """One fitted baseline family."""

    source: str
    event_type: str
    clock_type: str
    window: str
    measure: str

    def label(self) -> str:
        return key(self.source, self.event_type, self.clock_type, self.window, self.measure)


@dataclass(frozen=True)
class FittedBaseline:
    """Frozen expected value lookup for one target/window/measure."""

    global_mean: float
    global_scale: float
    grouped_means: dict[str, dict[tuple[object, ...], float]] = field(default_factory=dict)
    grouped_scales: dict[str, dict[tuple[object, ...], float]] = field(default_factory=dict)
    grouped_counts: dict[str, dict[tuple[object, ...], int]] = field(default_factory=dict)
    model_type: str = "hierarchical_empirical"
    coefficients: dict[str, float] = field(default_factory=dict)
    poisson_columns: tuple[str, ...] = ()
    fit_note: str = ""


@dataclass(frozen=True)
class ActivitySurpriseArtifact:
    """Frozen fitted A5 state."""

    config: ActivitySurpriseConfig
    train_end: pd.Timestamp
    validation_end: pd.Timestamp
    baselines: dict[str, FittedBaseline]
    ratio_baselines: dict[str, FittedBaseline]
    searched_windows: dict[str, tuple[object, ...]]
    selected_windows: dict[str, tuple[object, ...]]
    model_version: str = A5_MODEL_VERSION


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A5",
        formula=(
            "observed activity minus frozen train-period population baseline, "
            "standardized by fitted residual scale"
        ),
        source_fields=(
            "rfqs.timestamp",
            "rfqs.size",
            "rfqs.dv01",
            "rfqs.cr01",
            "events.prediction_timestamp",
            "events.notional",
            "events.dv01",
            "events.cr01",
            "bonds.issuer_id",
        ),
        clock="calendar_time, rfq_event_time, trace_transaction_time",
        window="fast: 1d, 3d, last 5/10 RFQs or trades; slow: 5d, 10d, 20d, 40d, 60d, 120d, last 25/50 RFQs or trades",
        min_observations=3,
        missing_policy="NaN with quality flags when source, risk field, or fitted baseline is unavailable",
        expected_sign="positive means bond or issuer activity is above its frozen population baseline",
        feature_class="liquidity",
        point_in_time_dependencies=(
            "fit uses training rows only",
            "score uses source event time strictly before prediction timestamp",
            "validation/test rows cannot change frozen fitted baselines",
        ),
        computational_cost="O(prediction_rows * selected_windows * event_types)",
        version=A5_MODEL_VERSION,
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    calendar_windows: tuple[str, ...] = A5_CALENDAR_WINDOWS,
    epsilon: float = EPSILON,
    config: ActivitySurpriseConfig | None = None,
) -> pd.DataFrame:
    """Backward-compatible A5 compute path.

    For production research, call `fit()` on the training split and `score()`
    with the returned artifact. This helper fits the population baseline using
    the default chronological split so existing CLI calls keep working.
    """

    cfg = config or ActivitySurpriseConfig(calendar_windows=tuple(calendar_windows), selected_calendar_windows=tuple(calendar_windows), epsilon=epsilon)
    return score(bundle, fit(bundle, config=cfg))


def config_from_mapping(payload: dict[str, object]) -> ActivitySurpriseConfig:
    """Build A5 config from a YAML-loaded mapping."""

    selected = payload.get("selected_windows", {})
    split = payload.get("train_validation_split", {})
    risk = payload.get("risk_measures", {})
    rate_risk = risk.get("rate_risk", {}) if isinstance(risk, dict) else {}
    credit_risk = risk.get("credit_risk", {}) if isinstance(risk, dict) else {}
    return ActivitySurpriseConfig(
        calendar_windows=tuple(str(item) for item in payload.get("calendar_windows", A5_CALENDAR_WINDOWS)),
        rfq_event_windows=tuple(int(item) for item in payload.get("rfq_event_windows", A5_RFQ_EVENT_WINDOWS)),
        trade_event_windows=tuple(int(item) for item in payload.get("trade_event_windows", A5_TRADE_EVENT_WINDOWS)),
        event_types=tuple(str(item) for item in payload.get("event_types", ("inquiry", "firmup", "execution", "trace_trade"))),
        model_type=str(payload.get("model_type", "auto")),
        pooling_levels=tuple(str(item) for item in payload.get("pooling_levels", ("bond", "issuer", "liquidity", "rating_sector_maturity", "global"))),
        minimum_observations=int(payload.get("minimum_observations", 3)),
        epsilon=float(payload.get("epsilon", EPSILON)),
        winsorization=float(payload.get("winsorization", 0.99)),
        train_fraction=float(split.get("train_fraction", payload.get("train_fraction", 0.70))) if isinstance(split, dict) else 0.70,
        validation_fraction=float(split.get("validation_fraction", payload.get("validation_fraction", 0.15))) if isinstance(split, dict) else 0.15,
        selection_metric=str(payload.get("selection_metric", "validation_standardized_error")),
        selected_calendar_windows=tuple(str(item) for item in selected.get("calendar_windows", payload.get("selected_calendar_windows", A5_CALENDAR_WINDOWS))) if isinstance(selected, dict) else A5_CALENDAR_WINDOWS,
        selected_rfq_event_windows=tuple(int(item) for item in selected.get("rfq_event_windows", payload.get("selected_rfq_event_windows", A5_RFQ_EVENT_WINDOWS))) if isinstance(selected, dict) else A5_RFQ_EVENT_WINDOWS,
        selected_trade_event_windows=tuple(int(item) for item in selected.get("trade_event_windows", payload.get("selected_trade_event_windows", A5_TRADE_EVENT_WINDOWS))) if isinstance(selected, dict) else A5_TRADE_EVENT_WINDOWS,
        frozen_after_fit=bool(payload.get("frozen_after_fit", True)),
        slow_refit_frequency=str(payload.get("slow_refit_frequency", "monthly")),
        allow_static_bond_dv01_fallback=bool(rate_risk.get("allow_static_bond_fallback", payload.get("allow_static_bond_dv01_fallback", False))) if isinstance(rate_risk, dict) else False,
        allow_static_bond_cr01_fallback=bool(credit_risk.get("allow_static_bond_fallback", payload.get("allow_static_bond_cr01_fallback", False))) if isinstance(credit_risk, dict) else False,
        static_risk_unit=payload.get("static_risk_unit") if payload.get("static_risk_unit") is not None else (risk.get("static_risk_unit") if isinstance(risk, dict) else None),
    )


def fit(
    bundle: AlphaInputBundle,
    *,
    config: ActivitySurpriseConfig | None = None,
    train_end: pd.Timestamp | None = None,
    validation_end: pd.Timestamp | None = None,
) -> ActivitySurpriseArtifact:
    """Fit frozen population activity baselines from the training period only."""

    cfg = config or ActivitySurpriseConfig()
    context = _with_activity_measures(build_context(bundle), cfg)
    return _fit_context(context, cfg, train_end, validation_end)


def _fit_context(
    context: AlphaContext,
    config: ActivitySurpriseConfig,
    train_end: pd.Timestamp | None = None,
    validation_end: pd.Timestamp | None = None,
) -> ActivitySurpriseArtifact:
    cfg = config
    train_end, validation_end = _resolve_split(context.prediction_grid, cfg, train_end, validation_end)
    train_grid = context.prediction_grid[context.prediction_grid["prediction_timestamp"] <= train_end].copy()

    baselines: dict[str, FittedBaseline] = {}
    for baseline_key in _baseline_keys(cfg):
        observations = _training_observations(context, train_grid, baseline_key)
        baselines[baseline_key.label()] = _fit_baseline(observations, baseline_key, cfg)
    ratio_baselines = {}
    for name in ("execution_to_inquiry", "firmup_to_inquiry", "trace_to_rfq"):
        for window in cfg.calendar_windows:
            ratio_baselines[f"{name}:{window}"] = _fit_empirical_baseline(
                _ratio_training_observations(context, train_grid, name, str(window), cfg),
                cfg,
            )

    return ActivitySurpriseArtifact(
        config=cfg,
        train_end=train_end,
        validation_end=validation_end,
        baselines=baselines,
        ratio_baselines=ratio_baselines,
        searched_windows={
            "calendar_windows": cfg.calendar_windows,
            "rfq_event_windows": cfg.rfq_event_windows,
            "trade_event_windows": cfg.trade_event_windows,
        },
        selected_windows={
            "calendar_windows": cfg.selected_calendar_windows,
            "rfq_event_windows": cfg.selected_rfq_event_windows,
            "trade_event_windows": cfg.selected_trade_event_windows,
        },
    )


def score(bundle: AlphaInputBundle, artifact: ActivitySurpriseArtifact) -> pd.DataFrame:
    """Score A5 using a frozen fitted artifact."""

    context = _with_activity_measures(build_context(bundle), artifact.config)
    return _score_context(context, artifact)


def _score_context(context: AlphaContext, artifact: ActivitySurpriseArtifact) -> pd.DataFrame:
    if context.prediction_grid.empty:
        return context.prediction_grid.copy()
    rows: list[dict[str, object]] = []
    for prediction in context.prediction_grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        bond_id = str(prediction.bond_id)
        row: dict[str, object] = {
            "prediction_timestamp": asof,
            "bond_id": bond_id,
            "issuer_id": prediction.issuer_id,
        }
        for baseline_key in _baseline_keys(artifact.config, selected_only=True):
            _add_scored_baseline(row, context, bond_id, asof, baseline_key, artifact)
        _add_ratio_surprises(row, context, bond_id, asof, artifact)
        _add_issuer_comparisons(row, context, bond_id, asof, artifact)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["bond_id", "prediction_timestamp"]).reset_index(drop=True)


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
    """Compatibility hook used by the combined microstructure wrapper."""

    cfg = ActivitySurpriseConfig(
        calendar_windows=tuple(str(window) for window in calendar_windows),
        selected_calendar_windows=tuple(str(window) for window in calendar_windows),
        epsilon=epsilon,
    )
    prepared = _with_activity_measures(context, cfg)
    artifact = _fit_context(prepared, cfg)
    scored = _score_context(prepared, artifact)
    match = scored[(scored["bond_id"] == str(bond_id)) & (scored["prediction_timestamp"] == asof)]
    if not match.empty:
        row.update(match.iloc[0].drop(labels=["prediction_timestamp", "bond_id", "issuer_id"]).to_dict())


def _baseline_keys(config: ActivitySurpriseConfig, *, selected_only: bool = False) -> Iterable[BaselineKey]:
    calendar_windows = config.selected_calendar_windows if selected_only else config.calendar_windows
    rfq_event_windows = config.selected_rfq_event_windows if selected_only else config.rfq_event_windows
    trade_event_windows = config.selected_trade_event_windows if selected_only else config.trade_event_windows
    for source, event_type in (("rfq", "inquiry"), ("rfq", "firmup"), ("rfq", "execution"), ("trace", "trace_trade")):
        if event_type not in config.event_types:
            continue
        windows: list[tuple[str, str]] = [(str(window), "calendar") for window in calendar_windows]
        if source == "rfq":
            windows.extend((str(window), "event") for window in rfq_event_windows)
        else:
            windows.extend((str(window), "event") for window in trade_event_windows)
        for window, clock_type in windows:
            yield BaselineKey(source, event_type, clock_type, window, "event_count")
            for measure in _MEASURES:
                yield BaselineKey(source, event_type, clock_type, window, measure)
        if source == "rfq":
            for window in calendar_windows:
                yield BaselineKey(source, f"issuer_{event_type}", "calendar", str(window), "event_count")
                for measure in _MEASURES:
                    yield BaselineKey(source, f"issuer_{event_type}", "calendar", str(window), measure)
        if source == "trace":
            for window in calendar_windows:
                yield BaselineKey(source, "issuer_trace_trade", "calendar", str(window), "event_count")
                for measure in _MEASURES:
                    yield BaselineKey(source, "issuer_trace_trade", "calendar", str(window), measure)


def _add_scored_baseline(
    row: dict[str, object],
    context: AlphaContext,
    bond_id: str,
    asof: pd.Timestamp,
    baseline_key: BaselineKey,
    artifact: ActivitySurpriseArtifact,
) -> None:
    frame = _event_frame(context, baseline_key.source, baseline_key.event_type, bond_id, asof)
    observed_frame = _window(frame, asof, baseline_key.clock_type, baseline_key.window)
    observed = _measure_value(observed_frame, baseline_key.measure)
    baseline = artifact.baselines[baseline_key.label()]
    expected = _expected_value(baseline, context, bond_id, asof, artifact.config)
    scale = _scale_value(baseline, context, bond_id, asof, artifact.config, expected)
    prefix = key("a5", baseline_key.source, baseline_key.event_type, baseline_key.clock_type, baseline_key.window)
    metric_prefix = prefix if baseline_key.measure == "event_count" else key(prefix, baseline_key.measure)
    quality = _quality_flag(observed_frame, baseline_key.measure, expected)

    if baseline_key.measure == "event_count":
        row[f"{metric_prefix}_observed_count"] = observed
        row[f"{metric_prefix}_expected_count"] = expected
        row[f"{metric_prefix}_count_surprise"] = _raw_surprise(observed, expected)
        row[f"{metric_prefix}_standardized_count_surprise"] = _standardized_surprise(observed, expected, scale, artifact.config.epsilon)
    else:
        row[f"{metric_prefix}_observed"] = observed
        row[f"{metric_prefix}_expected"] = expected
        row[f"{metric_prefix}_standardized_surprise"] = _standardized_surprise(observed, expected, scale, artifact.config.epsilon)

    last_timestamp = observed_frame["timestamp"].max() if not observed_frame.empty else pd.NaT
    row[f"{metric_prefix}_last_observation_timestamp"] = last_timestamp
    row[f"{metric_prefix}_staleness_seconds"] = np.nan if pd.isna(last_timestamp) else float((asof - pd.Timestamp(last_timestamp)).total_seconds())
    row[f"{metric_prefix}_quality_flag"] = quality
    row[f"{metric_prefix}_model_version"] = artifact.model_version
    row[f"{metric_prefix}_model_type"] = baseline.model_type
    row[f"{metric_prefix}_fit_note"] = baseline.fit_note


def _add_ratio_surprises(row: dict[str, object], context: AlphaContext, bond_id: str, asof: pd.Timestamp, artifact: ActivitySurpriseArtifact) -> None:
    for window in artifact.config.selected_calendar_windows:
        rfq_prior = _window(_event_frame(context, "rfq", "inquiry", bond_id, asof), asof, "calendar", str(window))
        executions = _window(_event_frame(context, "rfq", "execution", bond_id, asof), asof, "calendar", str(window))
        firmups = _window(_event_frame(context, "rfq", "firmup", bond_id, asof), asof, "calendar", str(window))
        traces = _window(_event_frame(context, "trace", "trace_trade", bond_id, asof), asof, "calendar", str(window))
        inquiry_count = float(len(rfq_prior))
        prefix = key("a5", "ratios", "calendar", window)
        ratios = {
            "execution_to_inquiry": np.nan if inquiry_count == 0 else float(len(executions) / (inquiry_count + artifact.config.epsilon)),
            "firmup_to_inquiry": np.nan if inquiry_count == 0 else float(len(firmups) / (inquiry_count + artifact.config.epsilon)),
            "trace_to_rfq": np.nan if inquiry_count == 0 else float(len(traces) / (inquiry_count + artifact.config.epsilon)),
        }
        for name, observed in ratios.items():
            baseline = artifact.ratio_baselines[f"{name}:{window}"]
            expected = _expected_value(baseline, context, bond_id, asof, artifact.config)
            scale = _scale_value(baseline, context, bond_id, asof, artifact.config, expected)
            row[f"{prefix}_{name}_observed_ratio"] = observed
            row[f"{prefix}_{name}_expected_ratio"] = expected
            row[f"{prefix}_{name}_surprise"] = _raw_surprise(observed, expected)
            row[f"{prefix}_{name}_standardized_surprise"] = _standardized_surprise(observed, expected, scale, artifact.config.epsilon)


def _add_issuer_comparisons(row: dict[str, object], context: AlphaContext, bond_id: str, asof: pd.Timestamp, artifact: ActivitySurpriseArtifact) -> None:
    measures = ("event_count", "notional", "signed_notional", "gross_dv01", "signed_dv01", "gross_cr01", "signed_cr01")
    for source, event_type in (("rfq", "inquiry"), ("rfq", "firmup"), ("rfq", "execution"), ("trace", "trace_trade")):
        if event_type not in artifact.config.event_types:
            continue
        issuer_event_type = f"issuer_{event_type}"
        for window in artifact.config.selected_calendar_windows:
            for measure in measures:
                bond_key = BaselineKey(source, event_type, "calendar", str(window), measure)
                issuer_key = BaselineKey(source, issuer_event_type, "calendar", str(window), measure)
                bond_frame = _window(_event_frame(context, source, event_type, bond_id, asof), asof, "calendar", str(window))
                issuer_frame = _window(_event_frame(context, source, issuer_event_type, bond_id, asof), asof, "calendar", str(window))
                observed_bond = _measure_value(bond_frame, measure)
                observed_issuer = _measure_value(issuer_frame, measure)
                expected_bond = _expected_value(artifact.baselines[bond_key.label()], context, bond_id, asof, artifact.config)
                expected_issuer = _expected_value(artifact.baselines[issuer_key.label()], context, bond_id, asof, artifact.config)
                prefix = key("a5", "bond_vs_issuer", source, event_type, "calendar", window, measure)
                row[f"{prefix}_share"] = _safe_ratio(observed_bond, observed_issuer, artifact.config.epsilon)
                row[f"{prefix}_expected_share"] = _safe_ratio(expected_bond, expected_issuer, artifact.config.epsilon)
                row[f"{prefix}_share_surprise"] = _raw_surprise(row[f"{prefix}_share"], row[f"{prefix}_expected_share"])
                bond_baseline = artifact.baselines[bond_key.label()]
                issuer_baseline = artifact.baselines[issuer_key.label()]
                bond_scale = _scale_value(bond_baseline, context, bond_id, asof, artifact.config, expected_bond)
                issuer_scale = _scale_value(issuer_baseline, context, bond_id, asof, artifact.config, expected_issuer)
                row[f"{prefix}_standardized_surprise_spread"] = _standardized_surprise(
                    observed_bond, expected_bond, bond_scale, artifact.config.epsilon
                ) - _standardized_surprise(observed_issuer, expected_issuer, issuer_scale, artifact.config.epsilon)


def _training_observations(context: AlphaContext, grid: pd.DataFrame, baseline_key: BaselineKey) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for prediction in grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        bond_id = str(prediction.bond_id)
        frame = _event_frame(context, baseline_key.source, baseline_key.event_type, bond_id, asof)
        observed = _measure_value(_window(frame, asof, baseline_key.clock_type, baseline_key.window), baseline_key.measure)
        if not np.isfinite(observed):
            continue
        rows.append({**_context_values(context, bond_id, asof), "observed": observed})
    return pd.DataFrame(rows)


def _ratio_training_observations(
    context: AlphaContext,
    grid: pd.DataFrame,
    ratio_name: str,
    window: str,
    config: ActivitySurpriseConfig,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for prediction in grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        bond_id = str(prediction.bond_id)
        rfq_prior = _window(_event_frame(context, "rfq", "inquiry", bond_id, asof), asof, "calendar", window)
        inquiry_count = float(len(rfq_prior))
        if inquiry_count == 0:
            continue
        if ratio_name == "execution_to_inquiry":
            numerator = len(_window(_event_frame(context, "rfq", "execution", bond_id, asof), asof, "calendar", window))
        elif ratio_name == "firmup_to_inquiry":
            numerator = len(_window(_event_frame(context, "rfq", "firmup", bond_id, asof), asof, "calendar", window))
        elif ratio_name == "trace_to_rfq":
            numerator = len(_window(_event_frame(context, "trace", "trace_trade", bond_id, asof), asof, "calendar", window))
        else:
            continue
        rows.append({**_context_values(context, bond_id, asof), "observed": float(numerator / (inquiry_count + config.epsilon))})
    return pd.DataFrame(rows)


def _fit_baseline(observations: pd.DataFrame, baseline_key: BaselineKey, config: ActivitySurpriseConfig) -> FittedBaseline:
    if baseline_key.measure == "event_count" and config.model_type in {"poisson_glm", "auto"}:
        fitted = _fit_poisson_baseline(observations, config)
        if fitted is not None:
            return fitted
    return _fit_empirical_baseline(observations, config)


def _fit_poisson_baseline(observations: pd.DataFrame, config: ActivitySurpriseConfig) -> FittedBaseline | None:
    if observations.empty or len(observations) < max(10, config.minimum_observations * 3):
        return None
    try:
        frame = observations.copy()
        columns = ["hour", "weekday", "liquidity_bucket", "rating_bucket", "sector", "maturity_bucket"]
        design = pd.get_dummies(frame[columns].astype("string").fillna("missing"), drop_first=True, dtype=float)
        design = sm.add_constant(design, has_constant="add")
        model = sm.GLM(frame["observed"].astype(float), design, family=sm.families.Poisson())
        result = model.fit(maxiter=100, disp=0)
        params = result.params
        if not np.all(np.isfinite(params.to_numpy(dtype=float))):
            return None
        predictions = np.asarray(result.predict(design), dtype=float)
        if predictions.size == 0 or not np.all(np.isfinite(predictions)) or np.nanmax(predictions) <= 0:
            return None
        residuals = frame["observed"].to_numpy(dtype=float) - predictions
        scale = _finite_scale(residuals)
        coefficients = {str(name): float(value) for name, value in params.items()}
        return FittedBaseline(
            global_mean=float(np.nanmean(predictions)),
            global_scale=scale,
            grouped_means={},
            grouped_scales={},
            grouped_counts={},
            model_type="poisson_glm",
            coefficients=coefficients,
            poisson_columns=tuple(str(column) for column in design.columns),
            fit_note="poisson_glm_fit",
        )
    except Exception:
        return None


def _fit_empirical_baseline(observations: pd.DataFrame, config: ActivitySurpriseConfig) -> FittedBaseline:
    if observations.empty:
        return FittedBaseline(global_mean=np.nan, global_scale=np.nan, fit_note="no_training_observations")
    clean = observations.copy()
    if 0.0 < config.winsorization < 1.0:
        cap = float(clean["observed"].quantile(config.winsorization))
        floor = float(clean["observed"].quantile(1.0 - config.winsorization)) if (1.0 - config.winsorization) > 0 else None
        clean["observed"] = clean["observed"].clip(lower=floor, upper=cap)
    grouped_means: dict[str, dict[tuple[object, ...], float]] = {}
    grouped_scales: dict[str, dict[tuple[object, ...], float]] = {}
    grouped_counts: dict[str, dict[tuple[object, ...], int]] = {}
    for level in config.pooling_levels:
        columns = _pooling_columns(level)
        if not columns:
            continue
        grouped = clean.groupby(list(columns), dropna=False)["observed"].agg(["mean", "std", "count"]).reset_index()
        grouped = grouped[grouped["count"] >= config.minimum_observations]
        grouped_means[level] = {tuple(record[column] for column in columns): float(record["mean"]) for record in grouped.to_dict("records")}
        grouped_scales[level] = {
            tuple(record[column] for column in columns): _finite_scale(np.array([record["std"]], dtype=float))
            for record in grouped.to_dict("records")
        }
        grouped_counts[level] = {tuple(record[column] for column in columns): int(record["count"]) for record in grouped.to_dict("records")}
    return FittedBaseline(
        global_mean=float(clean["observed"].mean()),
        global_scale=_finite_scale(clean["observed"].to_numpy(dtype=float) - float(clean["observed"].mean())),
        grouped_means=grouped_means,
        grouped_scales=grouped_scales,
        grouped_counts=grouped_counts,
        model_type="hierarchical_empirical",
        fit_note="empirical_fallback",
    )


def _expected_value(baseline: FittedBaseline, context: AlphaContext, bond_id: str, asof: pd.Timestamp, config: ActivitySurpriseConfig) -> float:
    if baseline.model_type == "poisson_glm" and baseline.coefficients:
        return _poisson_expected_value(baseline, context, bond_id, asof)
    values = _context_values(context, bond_id, asof)
    for level in config.pooling_levels:
        columns = _pooling_columns(level)
        if not columns:
            continue
        lookup_key = tuple(values[column] for column in columns)
        level_values = baseline.grouped_means.get(level, {})
        if lookup_key in level_values:
            return level_values[lookup_key]
    return baseline.global_mean


def _scale_value(
    baseline: FittedBaseline,
    context: AlphaContext,
    bond_id: str,
    asof: pd.Timestamp,
    config: ActivitySurpriseConfig,
    expected: float,
) -> float:
    if baseline.model_type == "poisson_glm":
        return max(np.sqrt(abs(expected)), baseline.global_scale)
    values = _context_values(context, bond_id, asof)
    for level in config.pooling_levels:
        columns = _pooling_columns(level)
        if not columns:
            continue
        lookup_key = tuple(values[column] for column in columns)
        level_values = baseline.grouped_scales.get(level, {})
        if lookup_key in level_values and np.isfinite(level_values[lookup_key]):
            return level_values[lookup_key]
    return baseline.global_scale


def _poisson_expected_value(baseline: FittedBaseline, context: AlphaContext, bond_id: str, asof: pd.Timestamp) -> float:
    values = _context_values(context, bond_id, asof)
    categories = {
        "hour": str(values["hour"]),
        "weekday": str(values["weekday"]),
        "liquidity_bucket": str(values["liquidity_bucket"]),
        "rating_bucket": str(values["rating_bucket"]),
        "sector": str(values["sector"]),
        "maturity_bucket": str(values["maturity_bucket"]),
    }
    linear = baseline.coefficients.get("const", 0.0)
    for column in baseline.poisson_columns:
        if column == "const":
            continue
        for name, value in categories.items():
            dummy_name = f"{name}_{value}"
            if column == dummy_name:
                linear += baseline.coefficients.get(column, 0.0)
    return float(np.exp(np.clip(linear, -20.0, 20.0)))


def _event_frame(context: AlphaContext, source: str, event_type: str, bond_id: str, asof: pd.Timestamp) -> pd.DataFrame:
    issuer_mode = event_type.startswith("issuer_")
    base_type = event_type.removeprefix("issuer_")
    source_frame = context.rfqs if source == "rfq" else context.traces
    if source_frame.empty:
        return source_frame.copy()
    if issuer_mode:
        issuer_id = _issuer_id(context, bond_id)
        frame = source_frame[source_frame.get("issuer_id", pd.Series(index=source_frame.index, dtype="object")).astype(str) == str(issuer_id)].copy()
        frame = frame[frame["timestamp"] < asof].copy()
    else:
        frame = prior(source_frame, bond_id, asof)
    if source == "rfq":
        if base_type == "inquiry":
            return filter_event_kind(frame, ("inquiry", "firm_inquiry", "firm inquiry", "firm")).copy()
        if base_type == "firmup":
            return filter_event_kind(frame, ("firm_up", "firm-up", "firmup")).copy()
        if base_type == "execution":
            return filter_event_kind(frame, ("execution", "executed")).copy()
    return frame[frame["side"].isin([-1, 1])].copy()


def _window(frame: pd.DataFrame, asof: pd.Timestamp, clock_type: str, window: str) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    if clock_type == "event":
        return last_n(frame, int(window))
    return within_timedelta(frame, asof, _to_timedelta(window))


def _to_timedelta(window: str) -> pd.Timedelta:
    text = str(window).strip().lower()
    if text.endswith("h"):
        return pd.Timedelta(float(text[:-1]), unit="h")
    if text.endswith("d"):
        return pd.Timedelta(float(text[:-1]), unit="D")
    if text.endswith("m"):
        return pd.Timedelta(float(text[:-1]), unit="m")
    return pd.Timedelta(text)


def _measure_value(frame: pd.DataFrame, measure: str) -> float:
    if measure == "event_count":
        return float(len(frame))
    if frame.empty or measure not in frame.columns:
        return np.nan
    values = pd.to_numeric(frame[measure], errors="coerce")
    if values.notna().sum() == 0:
        return np.nan
    return float(values.sum())


def _with_activity_measures(context: AlphaContext, config: ActivitySurpriseConfig | None = None) -> AlphaContext:
    cfg = config or ActivitySurpriseConfig()
    return AlphaContext(
        prediction_grid=context.prediction_grid.copy(),
        rfqs=_prepare_activity_frame(context.rfqs, context.bonds, cfg),
        traces=_prepare_activity_frame(context.traces, context.bonds, cfg),
        quotes=context.quotes,
        bonds=context.bonds,
    )


def _prepare_activity_frame(frame: pd.DataFrame, bonds: pd.DataFrame, config: ActivitySurpriseConfig) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    prepared = frame.copy()
    if "issuer_id" not in prepared.columns:
        prepared["issuer_id"] = prepared["bond_id"].map(bonds["issuer_id"] if "issuer_id" in bonds.columns else {})
    prepared["notional"] = pd.to_numeric(prepared.get("notional", np.nan), errors="coerce")
    prepared["side"] = pd.to_numeric(prepared.get("side", np.nan), errors="coerce")
    prepared["signed_notional"] = prepared["side"] * prepared["notional"]
    for risk_name in ("dv01", "cr01"):
        if risk_name not in prepared.columns:
            mapped = _static_risk_fallback(prepared, bonds, risk_name, config)
            prepared[risk_name] = mapped if mapped is not None else np.nan
        prepared[risk_name] = pd.to_numeric(prepared[risk_name], errors="coerce")
        prepared[f"gross_{risk_name}"] = prepared[risk_name].abs()
        prepared[f"signed_{risk_name}"] = prepared["side"] * prepared[risk_name]
    return prepared.sort_values(["bond_id", "timestamp"]).reset_index(drop=True)


def _map_bond_column(frame: pd.DataFrame, bonds: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in bonds.columns:
        return None
    mapping = bonds[column]
    if "bond_id" in bonds.columns and bonds.index.name != "bond_id":
        mapping = bonds.set_index("bond_id")[column]
    return frame["bond_id"].map(mapping)


def _context_values(context: AlphaContext, bond_id: str, asof: pd.Timestamp) -> dict[str, object]:
    bond = context.bonds.loc[bond_id] if bond_id in context.bonds.index else pd.Series(dtype="object")
    return {
        "bond_id": bond_id,
        "issuer_id": _issuer_id(context, bond_id),
        "liquidity_bucket": _series_value(bond, "liquidity_bucket"),
        "rating_bucket": _series_value(bond, "rating_bucket", _series_value(bond, "rating")),
        "sector": _series_value(bond, "sector"),
        "maturity_bucket": _series_value(bond, "maturity_bucket"),
        "hour": int(asof.hour),
        "weekday": int(asof.weekday()),
    }


def _pooling_columns(level: str) -> tuple[str, ...]:
    return {
        "bond": ("bond_id", "hour", "weekday"),
        "issuer": ("issuer_id", "hour", "weekday"),
        "liquidity": ("liquidity_bucket", "hour", "weekday"),
        "rating_sector_maturity": ("rating_bucket", "sector", "maturity_bucket", "hour", "weekday"),
        "global": ("hour", "weekday"),
    }.get(level, ())


def _issuer_id(context: AlphaContext, bond_id: str) -> object:
    if bond_id in context.bonds.index and "issuer_id" in context.bonds.columns:
        return context.bonds.loc[bond_id, "issuer_id"]
    return np.nan


def _series_value(row: pd.Series, column: str, default: object = np.nan) -> object:
    if row.empty or column not in row or pd.isna(row[column]):
        return default
    return row[column]


def _raw_surprise(observed: float, expected: float) -> float:
    if not np.isfinite(observed) or not np.isfinite(expected):
        return np.nan
    return float(observed - expected)


def _static_risk_fallback(
    frame: pd.DataFrame,
    bonds: pd.DataFrame,
    risk_name: str,
    config: ActivitySurpriseConfig,
) -> pd.Series | None:
    allowed = risk_name == "dv01" and config.allow_static_bond_dv01_fallback
    allowed = allowed or (risk_name == "cr01" and config.allow_static_bond_cr01_fallback)
    if not allowed or not config.static_risk_unit:
        return None
    mapped = _map_bond_column(frame, bonds, risk_name)
    if mapped is None:
        return None
    unit = config.static_risk_unit.lower()
    if unit in {"event", "trade", "traded"}:
        return mapped
    if unit in {"per_1mm_notional", "per_mm_notional"}:
        return mapped * pd.to_numeric(frame["notional"], errors="coerce") / 1_000_000.0
    if unit in {"per_unit_notional", "per_notional"}:
        return mapped * pd.to_numeric(frame["notional"], errors="coerce")
    return None


def _standardized_surprise(observed: float, expected: float, scale: float, epsilon: float) -> float:
    if not np.isfinite(observed) or not np.isfinite(expected) or not np.isfinite(scale):
        return np.nan
    return float((observed - expected) / (abs(scale) + epsilon))


def _finite_scale(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.nan
    if finite.size == 1:
        value = abs(float(finite[0]))
        return value if value > 0 else 1.0
    scale = float(np.nanstd(finite, ddof=1))
    return scale if np.isfinite(scale) and scale > 0 else 1.0


def _safe_ratio(numerator: float, denominator: float, epsilon: float) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or abs(denominator) <= epsilon:
        return np.nan
    return float(numerator / (denominator + np.sign(denominator) * epsilon))


def _quality_flag(frame: pd.DataFrame, measure: str, expected: float) -> str:
    if measure != "event_count" and (frame.empty or measure not in frame.columns or pd.to_numeric(frame[measure], errors="coerce").notna().sum() == 0):
        if "dv01" in measure:
            return "missing_dv01"
        if "cr01" in measure:
            return "missing_cr01"
        return "missing_measure"
    if not np.isfinite(expected):
        return "missing_baseline"
    if frame.empty:
        return "no_observations"
    return "ok"


def _resolve_split(
    grid: pd.DataFrame,
    config: ActivitySurpriseConfig,
    train_end: pd.Timestamp | None,
    validation_end: pd.Timestamp | None,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    if grid.empty:
        return pd.Timestamp.min, pd.Timestamp.min
    timestamps = pd.Series(pd.to_datetime(grid["prediction_timestamp"]).sort_values().unique())
    if train_end is None:
        train_idx = max(0, min(len(timestamps) - 1, int(np.floor((len(timestamps) - 1) * config.train_fraction))))
        train_end = pd.Timestamp(timestamps.iloc[train_idx])
    if validation_end is None:
        val_fraction = min(0.99, config.train_fraction + config.validation_fraction)
        val_idx = max(0, min(len(timestamps) - 1, int(np.floor((len(timestamps) - 1) * val_fraction))))
        validation_end = pd.Timestamp(timestamps.iloc[val_idx])
    return pd.Timestamp(train_end), pd.Timestamp(validation_end)
