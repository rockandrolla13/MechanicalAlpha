"""A5: multi-clock activity surprise."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_CALENDAR_WINDOWS, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, filter_event_kind, key, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A5",
        formula="recent activity minus as-of historical same-hour baseline, divided by baseline scale",
        source_fields=("rfqs.timestamp", "rfqs.size", "events.prediction_timestamp", "events.notional"),
        clock="calendar_time",
        window="30m, 2h",
        min_observations=3,
        missing_policy="NaN when the source or as-of baseline is too sparse",
        expected_sign="positive means activity is above its own time-of-day baseline",
        feature_class="liquidity",
        point_in_time_dependencies=("source event time < prediction timestamp", "baseline uses prior same-hour rows only"),
        computational_cost="O(prediction_rows * prior_rows)",
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    calendar_windows: tuple[str, ...] = DEFAULT_CALENDAR_WINDOWS,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, calendar_windows=calendar_windows, epsilon=epsilon)


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
        prior_rows = prior(source, bond_id, asof)
        for window in calendar_windows:
            delta = pd.Timedelta(str(window))
            recent = within_timedelta(prior_rows, asof, delta)
            baseline = _same_hour_prior_counts(prior_rows, asof, delta)
            prefix = key("a5", source_name, window)
            row[f"{prefix}_event_count_surprise"] = _surprise(float(len(recent)), baseline)
            recent_notional = float(recent["notional"].dropna().sum())
            baseline_notional = _same_hour_prior_notional(prior_rows, asof, delta)
            row[f"{prefix}_notional_surprise"] = _surprise(recent_notional, baseline_notional)

    prior_rfqs = prior(context.rfqs, bond_id, asof)
    prior_trace = prior(context.traces, bond_id, asof)
    for window in calendar_windows:
        delta = pd.Timedelta(str(window))
        inquiries = max(len(within_timedelta(prior_rfqs, asof, delta)), 0)
        executions = len(within_timedelta(filter_event_kind(prior_rfqs, ("execution", "executed")), asof, delta))
        firmups = len(within_timedelta(filter_event_kind(prior_rfqs, ("firm_up", "firm-up", "firmup")), asof, delta))
        trace_count = len(within_timedelta(prior_trace, asof, delta))
        prefix = key("a5", "ratios", window)
        row[f"{prefix}_execution_to_inquiry_ratio"] = np.nan if inquiries == 0 else executions / (inquiries + epsilon)
        row[f"{prefix}_firmup_to_inquiry_ratio"] = np.nan if inquiries == 0 else firmups / (inquiries + epsilon)
        row[f"{prefix}_trace_to_rfq_activity_ratio"] = np.nan if inquiries == 0 else trace_count / (inquiries + epsilon)


def _same_hour_prior_counts(prior_rows: pd.DataFrame, asof: pd.Timestamp, delta: pd.Timedelta) -> np.ndarray:
    if prior_rows.empty:
        return np.array([], dtype=float)
    same_hour = prior_rows[prior_rows["timestamp"].dt.hour == asof.hour]
    dates = same_hour["timestamp"].dt.normalize().drop_duplicates().tolist()
    return np.array([len(within_timedelta(same_hour, pd.Timestamp(date) + (asof - asof.normalize()), delta)) for date in dates])


def _same_hour_prior_notional(prior_rows: pd.DataFrame, asof: pd.Timestamp, delta: pd.Timedelta) -> np.ndarray:
    if prior_rows.empty:
        return np.array([], dtype=float)
    same_hour = prior_rows[prior_rows["timestamp"].dt.hour == asof.hour]
    dates = same_hour["timestamp"].dt.normalize().drop_duplicates().tolist()
    return np.array(
        [
            float(within_timedelta(same_hour, pd.Timestamp(date) + (asof - asof.normalize()), delta)["notional"].dropna().sum())
            for date in dates
        ]
    )


def _surprise(value: float, baseline: np.ndarray) -> float:
    finite = baseline[np.isfinite(baseline)]
    if finite.size < 3:
        return np.nan
    scale = float(np.nanstd(finite, ddof=1))
    if scale == 0.0:
        scale = 1.0
    return float((value - float(np.nanmean(finite))) / scale)

