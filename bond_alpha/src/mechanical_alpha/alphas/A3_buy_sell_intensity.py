"""A3: buy/sell intensity pressure."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_EWMA_HALFLIVES, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, key, nan_if_no_obs, prior
from mechanical_alpha.contracts import AlphaInputBundle


@dataclass(frozen=True)
class IntensityConfig:
    """Configuration for fitted buy/sell intensity pressure."""

    half_life_candidates: tuple[str, ...] = ("1d", "2d", "5d", "10d", "20d", "40d")
    forecast_window: str = "1d"
    clock_measures: tuple[str, ...] = ("count", "cr01")
    minimum_observations: int = 5
    epsilon: float = EPSILON


@dataclass(frozen=True)
class FittedIntensity:
    """Frozen baseline and selected EWMA half-life for one source and side."""

    source: str
    side: int
    measure: str
    selected_half_life: str
    baseline_intensity_per_second: float
    train_events: int
    train_measure_total: float
    train_exposure_seconds: float
    poisson_deviance: float
    method: str


@dataclass(frozen=True)
class IntensityArtifact:
    """Train-fitted A3 baseline rates and selected half-lives."""

    config: IntensityConfig
    fitted: dict[str, FittedIntensity] = field(default_factory=dict)


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A3",
        formula="train-selected elapsed-time EWMA count and CR01 intensities compared with frozen empirical baselines",
        source_fields=("rfqs.side", "rfqs.timestamp", "rfqs.cr01", "events.side", "events.prediction_timestamp", "events.cr01"),
        clock="calendar_time_and_cr01_activity",
        window="half-life candidates in trading days, default 1d, 2d, 5d, 10d, 20d, 40d; fitted separately for count and CR01 clocks",
        min_observations=1,
        missing_policy="NaN when no prior observations exist; CR01 features are NaN when CR01 is absent; fitted baseline falls back to pooled empirical rates when sparse",
        expected_sign="higher buy-minus-sell surprise means abnormal customer-buy arrival pressure or abnormal customer-buy CR01 risk flow",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp", "half-life and baselines fitted on training rows only"),
        computational_cost="O(prediction_rows * prior_rows)",
        version="0.3.0",
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    ewma_halflives: tuple[str, ...] = DEFAULT_EWMA_HALFLIVES,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, ewma_halflives=ewma_halflives, epsilon=epsilon)


def fit(
    bundle: AlphaInputBundle,
    *,
    config: IntensityConfig | None = None,
    train_end: pd.Timestamp | None = None,
) -> IntensityArtifact:
    """Fit side-specific Poisson baselines and select EWMA half-lives from training data."""

    cfg = config or IntensityConfig()
    context = build_context(bundle)
    fitted: dict[str, FittedIntensity] = {}
    for source_name, source in _sources(context).items():
        training = _training_rows(source, train_end)
        exposure = _exposure_seconds(training)
        for measure in cfg.clock_measures:
            global_total = _measure_total(training, measure)
            global_rate = _safe_rate(global_total, exposure)
            for side in (1, -1):
                side_training = training[training["side"] == side]
                side_total = _measure_total(side_training, measure)
                baseline = _safe_rate(side_total, exposure)
                if not np.isfinite(baseline) or baseline <= 0:
                    baseline = global_rate / 2.0 if global_rate > 0 else np.nan
                selected_half_life, deviance = _select_half_life(training, side, measure, cfg)
                method = _method_name(measure)
                if measure != "count" and not _measure_available(training, measure):
                    method = f"missing_{measure}"
                elif len(side_training) < cfg.minimum_observations or not np.isfinite(baseline):
                    method = "pooled_empirical_fallback"
                item = FittedIntensity(
                    source=source_name,
                    side=side,
                    measure=measure,
                    selected_half_life=selected_half_life,
                    baseline_intensity_per_second=float(baseline) if np.isfinite(baseline) else np.nan,
                    train_events=int(len(side_training)),
                    train_measure_total=float(side_total) if np.isfinite(side_total) else np.nan,
                    train_exposure_seconds=float(exposure),
                    poisson_deviance=float(deviance),
                    method=method,
                )
                fitted[f"{source_name}:{side}:{measure}"] = item
                if measure == "count":
                    fitted[f"{source_name}:{side}"] = item
    return IntensityArtifact(config=cfg, fitted=fitted)


def score(bundle: AlphaInputBundle, artifact: IntensityArtifact) -> pd.DataFrame:
    """Score A3 with frozen train-fitted half-lives and baseline intensities."""

    context = build_context(bundle)
    half_lives = tuple(
        sorted(
            {item.selected_half_life for key, item in artifact.fitted.items() if _is_primary_fit_key(key)},
            key=lambda value: _parse_timedelta(value).total_seconds(),
        )
    )
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
        ewma_halflives=half_lives,
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
    artifact: IntensityArtifact | None = None,
) -> None:
    for source_name, source in _sources(context).items():
        valid_prior = prior(source[source["side"].isin([-1, 1])], bond_id, asof)
        for half_life in ewma_halflives:
            decay = _parse_timedelta(half_life)
            buy_intensity = _ewma_intensity(valid_prior[valid_prior["side"] == 1], asof, decay)
            sell_intensity = _ewma_intensity(valid_prior[valid_prior["side"] == -1], asof, decay)
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
            if _measure_available(valid_prior, "cr01"):
                buy_cr01_intensity = _ewma_measure_intensity(valid_prior[valid_prior["side"] == 1], asof, decay, "cr01")
                sell_cr01_intensity = _ewma_measure_intensity(valid_prior[valid_prior["side"] == -1], asof, decay, "cr01")
                row[f"{prefix}_buy_cr01_intensity"] = buy_cr01_intensity
                row[f"{prefix}_sell_cr01_intensity"] = sell_cr01_intensity
                row[f"{prefix}_cr01_intensity_difference"] = nan_if_no_obs(
                    buy_cr01_intensity,
                    sell_cr01_intensity,
                    buy_cr01_intensity - sell_cr01_intensity,
                )
        if artifact is not None:
            _write_fitted_features(row, source_name, valid_prior, asof, artifact)


def _ewma_intensity(frame: pd.DataFrame, asof: pd.Timestamp, half_life: pd.Timedelta) -> float:
    return _ewma_measure_intensity(frame, asof, half_life, "count")


def _ewma_measure_intensity(frame: pd.DataFrame, asof: pd.Timestamp, half_life: pd.Timedelta, measure: str) -> float:
    if frame.empty:
        return np.nan
    ages = (asof - frame["timestamp"]).dt.total_seconds().to_numpy(dtype=float)
    half_life_seconds = max(float(half_life.total_seconds()), 1.0)
    weights = np.exp(-np.log(2.0) * ages / half_life_seconds)
    values = _measure_values(frame, measure)
    if values is None:
        return np.nan
    return float(np.nansum(values * weights) / half_life_seconds)


def _sources(context: AlphaContext) -> dict[str, pd.DataFrame]:
    return {"rfq": context.rfqs, "trace": context.traces}


def _training_rows(source: pd.DataFrame, train_end: pd.Timestamp | None) -> pd.DataFrame:
    if source.empty:
        return source.copy()
    training = source[source["side"].isin([-1, 1])].copy()
    if train_end is not None:
        training = training[training["timestamp"] < pd.Timestamp(train_end)].copy()
    return training.sort_values("timestamp").reset_index(drop=True)


def _exposure_seconds(training: pd.DataFrame) -> float:
    if len(training) < 2:
        return np.nan
    span = (training["timestamp"].max() - training["timestamp"].min()).total_seconds()
    return float(span) if span > 0 else np.nan


def _safe_rate(total: float, exposure_seconds: float) -> float:
    if not np.isfinite(exposure_seconds) or exposure_seconds <= 0:
        return np.nan
    if not np.isfinite(total):
        return np.nan
    return float(total / exposure_seconds)


def _select_half_life(training: pd.DataFrame, side: int, measure: str, config: IntensityConfig) -> tuple[str, float]:
    if len(training) < config.minimum_observations:
        return config.half_life_candidates[0], np.nan
    if measure != "count" and not _measure_available(training, measure):
        return config.half_life_candidates[0], np.nan
    forecast = _parse_timedelta(config.forecast_window)
    best = (config.half_life_candidates[0], np.inf)
    for half_life in config.half_life_candidates:
        deviance = _forecast_deviance_for_half_life(
            training,
            side,
            measure,
            _parse_timedelta(half_life),
            forecast,
            config.epsilon,
        )
        if np.isfinite(deviance) and deviance < best[1]:
            best = (half_life, deviance)
    return best if np.isfinite(best[1]) else (config.half_life_candidates[0], np.nan)


def _forecast_deviance_for_half_life(
    training: pd.DataFrame,
    side: int,
    measure: str,
    half_life: pd.Timedelta,
    forecast_window: pd.Timedelta,
    epsilon: float,
) -> float:
    if training.empty:
        return np.nan
    horizon_seconds = max(float(forecast_window.total_seconds()), 1.0)
    y_true: list[float] = []
    y_pred: list[float] = []
    timestamps = training["timestamp"].reset_index(drop=True)
    sides = training["side"].reset_index(drop=True)
    for idx, asof in enumerate(timestamps):
        past = training.iloc[:idx]
        future_mask = (timestamps > asof) & (timestamps <= asof + forecast_window) & (sides == side)
        future = training[future_mask]
        observed = _measure_total(future, measure)
        intensity = _ewma_measure_intensity(past[past["side"] == side], pd.Timestamp(asof), half_life, measure)
        if not np.isfinite(intensity):
            continue
        expected = max(float(intensity * horizon_seconds), epsilon)
        y_true.append(observed)
        y_pred.append(expected)
    if not y_true:
        return np.nan
    observed_arr = np.asarray(y_true, dtype=float)
    expected_arr = np.asarray(y_pred, dtype=float)
    terms = expected_arr - observed_arr
    positive = observed_arr > 0
    terms[positive] += observed_arr[positive] * np.log(observed_arr[positive] / expected_arr[positive])
    return float(2.0 * np.sum(terms))


def _write_fitted_features(
    row: dict[str, object],
    source_name: str,
    valid_prior: pd.DataFrame,
    asof: pd.Timestamp,
    artifact: IntensityArtifact,
) -> None:
    for measure in artifact.config.clock_measures:
        buy = artifact.fitted.get(f"{source_name}:1:{measure}")
        sell = artifact.fitted.get(f"{source_name}:-1:{measure}")
        if buy is None or sell is None:
            continue
        buy_intensity = _ewma_measure_intensity(
            valid_prior[valid_prior["side"] == 1],
            asof,
            _parse_timedelta(buy.selected_half_life),
            measure,
        )
        sell_intensity = _ewma_measure_intensity(
            valid_prior[valid_prior["side"] == -1],
            asof,
            _parse_timedelta(sell.selected_half_life),
            measure,
        )
        buy_surprise = buy_intensity - buy.baseline_intensity_per_second if np.isfinite(buy_intensity) else np.nan
        sell_surprise = sell_intensity - sell.baseline_intensity_per_second if np.isfinite(sell_intensity) else np.nan
        prefix = key("a3", source_name, "fitted" if measure == "count" else f"fitted_{measure}")
        row[f"{prefix}_buy_intensity"] = buy_intensity
        row[f"{prefix}_sell_intensity"] = sell_intensity
        row[f"{prefix}_buy_expected_intensity"] = buy.baseline_intensity_per_second
        row[f"{prefix}_sell_expected_intensity"] = sell.baseline_intensity_per_second
        row[f"{prefix}_buy_intensity_surprise"] = buy_surprise
        row[f"{prefix}_sell_intensity_surprise"] = sell_surprise
        row[f"{prefix}_intensity_surprise_difference"] = nan_if_no_obs(buy_surprise, sell_surprise, buy_surprise - sell_surprise)
        row[f"{prefix}_log_surprise_ratio"] = nan_if_no_obs(
            buy_surprise,
            sell_surprise,
            log((max(buy_surprise, 0.0) + artifact.config.epsilon) / (max(sell_surprise, 0.0) + artifact.config.epsilon)),
        )
        row[f"{prefix}_buy_half_life"] = buy.selected_half_life
        row[f"{prefix}_sell_half_life"] = sell.selected_half_life
        row[f"{prefix}_buy_model_method"] = buy.method
        row[f"{prefix}_sell_model_method"] = sell.method


def _measure_values(frame: pd.DataFrame, measure: str) -> np.ndarray | None:
    if measure == "count":
        return np.ones(len(frame), dtype=float)
    if measure not in frame.columns:
        return None
    values = pd.to_numeric(frame[measure], errors="coerce").to_numpy(dtype=float)
    if np.all(~np.isfinite(values)):
        return None
    return np.where(np.isfinite(values), np.maximum(values, 0.0), 0.0)


def _measure_total(frame: pd.DataFrame, measure: str) -> float:
    values = _measure_values(frame, measure)
    if values is None:
        return np.nan
    return float(np.sum(values))


def _measure_available(frame: pd.DataFrame, measure: str) -> bool:
    return _measure_values(frame, measure) is not None


def _method_name(measure: str) -> str:
    return "empirical_poisson" if measure == "count" else f"empirical_{measure}_rate"


def _is_primary_fit_key(value: str) -> bool:
    return value.count(":") == 2


def _parse_timedelta(value: object) -> pd.Timedelta:
    text = str(value).strip().lower()
    if text.endswith("d") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="D")
    if text.endswith("h") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="h")
    if text.endswith("m") and text[:-1]:
        return pd.Timedelta(float(text[:-1]), unit="m")
    return pd.Timedelta(text)
