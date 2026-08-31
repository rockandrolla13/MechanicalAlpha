"""Typed point-in-time operators for corporate-bond state features."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite, log
from statistics import median
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Observation:
    """One as-of observation passed to a state operator."""

    timestamp: pd.Timestamp
    value: float | None = None
    side: int | None = None
    weight: float | None = None
    x: float | None = None
    y: float | None = None
    baseline_mean: float | None = None
    baseline_std: float | None = None
    predicted: float | None = None


@dataclass(frozen=True)
class OperatorResult:
    """Standard operator output.

    `value=None` means no valid estimate exists.
    It is distinct from a true numeric zero.
    """

    value: float | int | None
    observation_count: int
    effective_sample_size: float
    last_observation_time: pd.Timestamp | None
    staleness_seconds: float | None
    quality_flags: tuple[str, ...] = ()


def result_for(
    value: float | int | None,
    observations: list[Observation],
    as_of: pd.Timestamp,
    flags: Iterable[str] = (),
) -> OperatorResult:
    """Build a standard result from an operator value and observations."""

    last_time = max((obs.timestamp for obs in observations), default=None)
    staleness = None
    if last_time is not None:
        staleness = (as_of - last_time).total_seconds()
    clean_flags = list(dict.fromkeys(flags))
    if not observations:
        clean_flags.append("no_observations")
    if value is None:
        clean_flags.append("missing_value")
    elif isinstance(value, float) and not isfinite(value):
        clean_flags.extend(["missing_value", "non_finite"])
        value = None
    return OperatorResult(value, len(observations), float(len(observations)), last_time, staleness, tuple(clean_flags))


def values(observations: list[Observation]) -> list[float]:
    return [float(obs.value) for obs in observations if obs.value is not None and isfinite(float(obs.value))]


def sides(observations: list[Observation]) -> list[int]:
    return [int(obs.side) for obs in observations if obs.side in (-1, 1)]


def count(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    return result_for(len(observations), observations, as_of)


def signed_count(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    valid = sides(observations)
    return result_for(sum(valid), observations, as_of, _flag_if(len(valid) != len(observations), "missing_side"))


def sum_value(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    return result_for(sum(vals) if vals else None, observations, as_of)


def signed_sum(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    total = 0.0
    used = 0
    for obs in observations:
        if obs.value is None or obs.side not in (-1, 1):
            continue
        total += float(obs.value) * int(obs.side)
        used += 1
    return result_for(total if used else None, observations, as_of, _flag_if(used != len(observations), "missing_value_or_side"))


def mean(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    return result_for(float(np.mean(vals)) if vals else None, observations, as_of)


def weighted_mean(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals: list[float] = []
    weights: list[float] = []
    for obs in observations:
        if obs.value is None or obs.weight is None:
            continue
        weight = float(obs.weight)
        if weight <= 0:
            continue
        vals.append(float(obs.value))
        weights.append(weight)
    if not vals or sum(weights) <= 0:
        return result_for(None, observations, as_of, ("missing_value_or_weight",))
    return result_for(float(np.average(vals, weights=weights)), observations, as_of)


def vwap(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    return weighted_mean(observations, as_of)


def minimum(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    return result_for(min(vals) if vals else None, observations, as_of)


def maximum(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    return result_for(max(vals) if vals else None, observations, as_of)


def first(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    for obs in sorted(observations, key=lambda item: item.timestamp):
        if obs.value is not None:
            return result_for(float(obs.value), observations, as_of)
    return result_for(None, observations, as_of)


def last(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    for obs in sorted(observations, key=lambda item: item.timestamp, reverse=True):
        if obs.value is not None:
            return result_for(float(obs.value), observations, as_of)
    return result_for(None, observations, as_of)


def percentile(observations: list[Observation], as_of: pd.Timestamp, q: float = 50.0) -> OperatorResult:
    vals = values(observations)
    if not vals:
        return result_for(None, observations, as_of)
    return result_for(float(np.percentile(vals, q)), observations, as_of)


def std(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    if len(vals) < 2:
        return result_for(None, observations, as_of, ("insufficient_observations",))
    return result_for(float(np.std(vals, ddof=1)), observations, as_of)


def mad(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    if not vals:
        return result_for(None, observations, as_of)
    med = median(vals)
    return result_for(float(median(abs(value - med) for value in vals)), observations, as_of)


def ewma_elapsed(
    observations: list[Observation],
    as_of: pd.Timestamp,
    half_life_seconds: float,
) -> OperatorResult:
    vals = values(observations)
    if not vals:
        return result_for(None, observations, as_of)
    if half_life_seconds <= 0:
        raise ValueError("half_life_seconds must be positive")
    weighted_values = []
    weights = []
    for obs in observations:
        if obs.value is None:
            continue
        age = max(0.0, (as_of - obs.timestamp).total_seconds())
        weight = exp(-log(2.0) * age / half_life_seconds)
        weighted_values.append(float(obs.value) * weight)
        weights.append(weight)
    if not weights:
        return result_for(None, observations, as_of)
    return result_for(float(sum(weighted_values) / sum(weights)), observations, as_of)


def run_length(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    ordered = [obs for obs in sorted(observations, key=lambda item: item.timestamp) if obs.side in (-1, 1)]
    if not ordered:
        return result_for(None, observations, as_of, ("missing_side",))
    last_side = ordered[-1].side
    length = 0
    for obs in reversed(ordered):
        if obs.side != last_side:
            break
        length += 1
    return result_for(length * int(last_side), observations, as_of)


def time_since_last_event(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    last_time = max((obs.timestamp for obs in observations), default=None)
    if last_time is None:
        return result_for(None, observations, as_of)
    return result_for((as_of - last_time).total_seconds(), observations, as_of)


def intensity(observations: list[Observation], as_of: pd.Timestamp, window_seconds: float) -> OperatorResult:
    if window_seconds <= 0:
        raise ValueError("window_seconds must be positive")
    return result_for(len(observations) / window_seconds, observations, as_of)


def robust_slope(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    pairs = [(float(obs.x), float(obs.y)) for obs in observations if obs.x is not None and obs.y is not None]
    if len(pairs) < 2:
        return result_for(None, observations, as_of, ("insufficient_observations",))
    slopes = []
    for i, (x_i, y_i) in enumerate(pairs):
        for x_j, y_j in pairs[i + 1 :]:
            if x_j != x_i:
                slopes.append((y_j - y_i) / (x_j - x_i))
    if not slopes:
        return result_for(None, observations, as_of, ("zero_x_range",))
    return result_for(float(median(slopes)), observations, as_of)


def robust_covariance(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    pairs = [(float(obs.x), float(obs.y)) for obs in observations if obs.x is not None and obs.y is not None]
    if len(pairs) < 2:
        return result_for(None, observations, as_of, ("insufficient_observations",))
    x = np.array([pair[0] for pair in pairs], dtype=float)
    y = np.array([pair[1] for pair in pairs], dtype=float)
    return result_for(float(np.median((x - np.median(x)) * (y - np.median(y)))), observations, as_of)


def robust_correlation(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    pairs = [(float(obs.x), float(obs.y)) for obs in observations if obs.x is not None and obs.y is not None]
    if len(pairs) < 2:
        return result_for(None, observations, as_of, ("insufficient_observations",))
    x = np.array([pair[0] for pair in pairs], dtype=float)
    y = np.array([pair[1] for pair in pairs], dtype=float)
    x_mad = np.median(np.abs(x - np.median(x)))
    y_mad = np.median(np.abs(y - np.median(y)))
    if x_mad == 0 or y_mad == 0:
        return result_for(None, observations, as_of, ("zero_dispersion",))
    corr = np.median((x - np.median(x)) * (y - np.median(y))) / (x_mad * y_mad)
    return result_for(float(np.clip(corr, -1.0, 1.0)), observations, as_of)


def rolling_rank(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    if not vals:
        return result_for(None, observations, as_of)
    last_value = vals[-1]
    rank = (sum(value <= last_value for value in vals) - 0.5) / len(vals)
    return result_for(float(rank), observations, as_of)


def cross_sectional_rank(value: float | None, cross_section: Iterable[float], as_of: pd.Timestamp) -> OperatorResult:
    vals = [float(item) for item in cross_section if isfinite(float(item))]
    if value is None or not vals:
        return OperatorResult(None, len(vals), float(len(vals)), None, None, ("missing_value",))
    rank = (sum(item <= float(value) for item in vals) - 0.5) / len(vals)
    return OperatorResult(float(rank), len(vals), float(len(vals)), as_of, 0.0, ())


def cross_sectional_rank_from_window(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    vals = values(observations)
    if not vals:
        return result_for(None, observations, as_of)
    return cross_sectional_rank(vals[-1], vals, as_of)


def time_of_day_zscore(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    if not observations:
        return result_for(None, observations, as_of)
    obs = observations[-1]
    if obs.value is None or obs.baseline_mean is None or obs.baseline_std is None:
        return result_for(None, observations, as_of, ("missing_baseline",))
    if obs.baseline_std <= 0:
        return result_for(None, observations, as_of, ("zero_baseline_std",))
    return result_for((float(obs.value) - float(obs.baseline_mean)) / float(obs.baseline_std), observations, as_of)


def residual(observations: list[Observation], as_of: pd.Timestamp) -> OperatorResult:
    if not observations:
        return result_for(None, observations, as_of)
    obs = observations[-1]
    if obs.value is None or obs.predicted is None:
        return result_for(None, observations, as_of, ("missing_prediction",))
    return result_for(float(obs.value) - float(obs.predicted), observations, as_of)


OPERATORS = {
    "count": count,
    "signed_count": signed_count,
    "sum": sum_value,
    "signed_sum": signed_sum,
    "mean": mean,
    "weighted_mean": weighted_mean,
    "vwap": vwap,
    "min": minimum,
    "max": maximum,
    "first": first,
    "last": last,
    "percentile": percentile,
    "std": std,
    "mad": mad,
    "ewma": ewma_elapsed,
    "run_length": run_length,
    "time_since_last_event": time_since_last_event,
    "intensity": intensity,
    "robust_slope": robust_slope,
    "robust_covariance": robust_covariance,
    "robust_correlation": robust_correlation,
    "rolling_rank": rolling_rank,
    "cross_sectional_rank": cross_sectional_rank_from_window,
    "time_of_day_zscore": time_of_day_zscore,
    "residual": residual,
}


def _flag_if(condition: bool, flag: str) -> tuple[str, ...]:
    return (flag,) if condition else ()
