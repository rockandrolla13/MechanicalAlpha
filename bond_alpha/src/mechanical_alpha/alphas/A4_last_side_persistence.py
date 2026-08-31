"""A4: last-side persistence and switching state."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_EVENT_WINDOWS, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, interaction, key, last_n, prior
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A4",
        formula="last side, same-side run length, time since side change, fraction of last N same-side events, interactions with imbalance, switching hazard",
        source_fields=("rfqs.side", "rfqs.timestamp", "events.side", "events.prediction_timestamp"),
        clock="rfq_event_time | trace_transaction_time",
        window="last_5, last_10, last_25",
        min_observations=1,
        missing_policy="NaN when no prior valid-side observations exist",
        expected_sign="positive last side means latest observable side was customer buy",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp",),
        computational_cost="O(prediction_rows * window_rows)",
    )


def compute(
    bundle: AlphaInputBundle,
    *,
    event_windows: tuple[int, ...] = DEFAULT_EVENT_WINDOWS,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    context = build_context(bundle)
    return compute_from_context(context, add_features, event_windows=event_windows, epsilon=epsilon)


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

