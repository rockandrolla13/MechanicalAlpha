"""A1: RFQ and TRACE count imbalance."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import DEFAULT_CALENDAR_WINDOWS, DEFAULT_EVENT_WINDOWS, EPSILON, FeatureDefinition, build_context, compute_from_context
from mechanical_alpha.alpha_common.context import AlphaContext, filter_event_kind, filter_firm_inquiries, key, last_n, prior, within_timedelta
from mechanical_alpha.contracts import AlphaInputBundle


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="A1",
        formula="(customer_buy_count_w - customer_sell_count_w) / (customer_buy_count_w + customer_sell_count_w + epsilon)",
        source_fields=("rfqs.side", "rfqs.timestamp", "events.side", "events.prediction_timestamp"),
        clock="calendar_time | rfq_event_time | trace_transaction_time",
        window="30m, 2h, last_5, last_10, last_25",
        min_observations=1,
        missing_policy="NaN when source table or valid side is unavailable; zero only when observations exist and signed counts net to zero",
        expected_sign="positive means recent customer-buy pressure",
        feature_class="directional",
        point_in_time_dependencies=("source event time < prediction timestamp",),
        computational_cost="O(prediction_rows * window_rows)",
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
    sources = {
        "rfq_all_inquiries": context.rfqs,
        "rfq_firm_inquiries": filter_firm_inquiries(context.rfqs),
        "rfq_firm_ups": filter_event_kind(context.rfqs, ("firm_up", "firm-up", "firmup")),
        "rfq_executions": filter_event_kind(context.rfqs, ("execution", "executed")),
        "trace_side_valid": context.traces[context.traces["side"].isin([-1, 1])],
    }
    for source_name, source in sources.items():
        for window in event_windows:
            hist = last_n(prior(source, bond_id, asof), int(window))
            _write_count(row, source_name, f"last_{window}", hist, epsilon)
        for window in calendar_windows:
            hist = within_timedelta(prior(source, bond_id, asof), asof, pd.Timedelta(str(window)))
            _write_count(row, source_name, str(window), hist, epsilon)


def _write_count(row: dict[str, object], source_name: str, window_name: str, hist: pd.DataFrame, epsilon: float) -> None:
    prefix = key("a1", source_name, window_name)
    valid = hist[hist["side"].isin([-1, 1])]
    buys = int((valid["side"] == 1).sum())
    sells = int((valid["side"] == -1).sum())
    total = buys + sells
    row[f"{prefix}_count_imbalance"] = np.nan if total == 0 else (buys - sells) / (total + epsilon)
    row[f"{prefix}_count"] = total

