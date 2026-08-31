import numpy as np
import pandas as pd

from mechanical_alpha.calendar import BusinessCalendar
from mechanical_alpha.events import CUSTOMER_BUY, CUSTOMER_SELL, dealer_inventory_change, normalize_customer_side
from mechanical_alpha.labels import LabelConfig, MeaningfulMoveThreshold, build_label_frame, label_coverage_report


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3"],
            "source": ["rfq", "rfq", "trace"],
            "bond_id": ["b1", "b1", "b1"],
            "issuer_id": ["i1", "i1", "i1"],
            "prediction_timestamp": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 11:00", "2026-01-02 12:00"]),
            "customer_side": [CUSTOMER_BUY, CUSTOMER_SELL, CUSTOMER_BUY],
            "executed": [True, False, False],
            "side_valid": [True, True, True],
            "executed_notional": [1_000_000.0, np.nan, np.nan],
            "execution_price": [100.00, np.nan, np.nan],
            "responded": [True, True, np.nan],
            "firmed_up": [True, False, np.nan],
            "won": [True, False, np.nan],
            "response_latency_ms": [250.0, 300.0, np.nan],
            "quoted_spread": [0.15, 0.20, np.nan],
            "quoted_price": [100.01, 99.95, np.nan],
            "realized_edge": [0.01, np.nan, np.nan],
        }
    )


def test_customer_side_and_dealer_inventory_signs_are_correct() -> None:
    assert normalize_customer_side("customer_buy") == 1
    assert normalize_customer_side("customer_sell") == -1
    assert dealer_inventory_change(CUSTOMER_BUY, 1_000_000) == -1_000_000
    assert dealer_inventory_change(CUSTOMER_SELL, 1_000_000) == 1_000_000


def test_dealer_markout_signs_are_correct() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1", "b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30"]),
            "fair_value": [100.0, 100.5],
        }
    )
    labels = build_label_frame(prediction_events=_events().iloc[[0]], fair_values=fair_values)
    assert labels.loc[0, "dealer_markout_30m"] == -0.5
    assert labels.loc[0, "dealer_toxic_30m"] == 1


def test_future_label_uses_only_prices_published_by_cutoff() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1", "b1", "b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 10:30"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 10:31"]),
            "revision_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 10:31"]),
            "fair_value": [100.0, 100.2, 101.0],
        }
    )
    labels = build_label_frame(prediction_events=_events().iloc[[0]], fair_values=fair_values)
    assert np.isclose(labels.loc[0, "price_target_30m"], 0.2)


def test_business_day_horizons_skip_weekends_and_holidays() -> None:
    calendar = BusinessCalendar.from_dates(["2026-01-05"])
    start = pd.Timestamp("2026-01-02 15:00")
    assert calendar.add_horizon(start, "1bd") == pd.Timestamp("2026-01-06 15:00")
    assert calendar.add_horizon(start, "5bd") == pd.Timestamp("2026-01-12 15:00")


def test_missing_or_stale_future_fair_value_is_censored_not_zero() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00"]),
            "fair_value": [100.0],
        }
    )
    labels = build_label_frame(
        prediction_events=_events().iloc[[0]],
        fair_values=fair_values,
        config=LabelConfig(max_future_fair_value_staleness=pd.Timedelta("10min")),
    )
    assert np.isnan(labels.loc[0, "price_target_30m"])
    assert labels.loc[0, "label_censored_30m"]


def test_end_of_history_labels_are_censored() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00"]),
            "fair_value": [100.0],
        }
    )
    labels = build_label_frame(prediction_events=_events().iloc[[0]], fair_values=fair_values)
    assert np.isnan(labels.loc[0, "price_target_5bd"])
    assert labels.loc[0, "label_censored_5bd"]


def test_composite_revisions_do_not_rewrite_historical_labels() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1", "b1", "b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 10:30"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 10:30"]),
            "revision_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 11:00"]),
            "fair_value": [100.0, 100.1, 99.0],
        }
    )
    labels = build_label_frame(prediction_events=_events().iloc[[0]], fair_values=fair_values)
    assert np.isclose(labels.loc[0, "price_target_30m"], 0.1)


def test_next_event_and_rfq_decision_labels_and_coverage_report() -> None:
    fair_values = pd.DataFrame(
        {
            "bond_id": ["b1", "b1", "b1"],
            "effective_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 11:00"]),
            "publication_time": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:30", "2026-01-02 11:00"]),
            "fair_value": [100.0, 100.1, 100.2],
        }
    )
    labels = build_label_frame(
        prediction_events=_events().iloc[[0]],
        fair_values=fair_values,
        event_stream=_events(),
        config=LabelConfig(
            meaningful_move={"30m": MeaningfulMoveThreshold(absolute_price_cents=5.0)},
            aggressive_hurdle={"30m": 0.05},
        ),
    )
    assert labels.loc[0, "next_rfq_side"] == CUSTOMER_SELL
    assert labels.loc[0, "time_to_next_rfq_seconds"] == 3600.0
    assert labels.loc[0, "next_trace_side"] == CUSTOMER_BUY
    assert labels.loc[0, "responded"] == True
    assert labels.loc[0, "aggressive_30m"] == 1
    assert labels.loc[0, "time_to_next_meaningful_fv_move_seconds"] == 1800.0
    assert labels.loc[0, "direction_first_meaningful_fv_move"] == 1

    coverage = label_coverage_report(
        labels,
        pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"], "rating": ["A"], "liquidity_bucket": ["liquid"]}),
        horizons=("30m",),
    )
    assert coverage.loc[0, "labeled_rows"] == 1
