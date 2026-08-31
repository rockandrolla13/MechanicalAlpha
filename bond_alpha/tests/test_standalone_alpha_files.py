import math

import pandas as pd

from mechanical_alpha.alphas import (
    A16_rfq_scarcity_disagreement,
    A1_rfq_count_imbalance,
    A2_rfq_notional_imbalance,
    A3_buy_sell_intensity,
    A4_last_side_persistence,
    A5_activity_surprise,
    A6_spread_conditioned_flow,
)
from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.registry import standalone_alpha_index
from mechanical_alpha.schema import SideConvention


def test_each_current_alpha_has_standalone_compute_and_description() -> None:
    bundle = _bundle()
    modules = (
        A1_rfq_count_imbalance,
        A2_rfq_notional_imbalance,
        A3_buy_sell_intensity,
        A4_last_side_persistence,
        A5_activity_surprise,
        A6_spread_conditioned_flow,
        A16_rfq_scarcity_disagreement,
    )

    for module in modules:
        description = module.describe()
        values = module.compute(bundle, event_windows=(5,), calendar_windows=("30m",)) if description.feature_id in {"A1", "A2"} else module.compute(bundle)
        assert description.feature_id
        assert {"prediction_timestamp", "bond_id", "issuer_id"}.issubset(values.columns)
        assert values.filter(regex=f"^{description.feature_id.lower()}_").shape[1] > 0


def test_standalone_a1_a2_a4_match_hand_calculation() -> None:
    bundle = _bundle()
    a1 = A1_rfq_count_imbalance.compute(bundle, event_windows=(5,), calendar_windows=("30m",))
    a2 = A2_rfq_notional_imbalance.compute(bundle, event_windows=(5,), calendar_windows=("30m",))
    a4 = A4_last_side_persistence.compute(bundle, event_windows=(5,))
    key = pd.Timestamp("2026-01-02 10:20:00")

    a1_row = a1[a1["prediction_timestamp"] == key].iloc[0]
    a2_row = a2[a2["prediction_timestamp"] == key].iloc[0]
    a4_row = a4[a4["prediction_timestamp"] == key].iloc[0]

    assert math.isclose(a1_row["a1_trace_side_valid_last_5_count_imbalance"], 1.0)
    assert math.isclose(a2_row["a2_trace_side_valid_last_5_raw_notional_imbalance"], 1.0)
    assert a4_row["a4_trace_last_side"] == 1
    assert a4_row["a4_trace_same_side_run_length"] == 2


def test_registry_indexes_standalone_alpha_files() -> None:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}
    assert index["A1"].module == "mechanical_alpha.alphas.A1_rfq_count_imbalance"
    assert index["A16"].status == "implemented"


def _bundle() -> object:
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "issuer_id": ["iss1"],
            "sector": ["industrial"],
            "rating": ["BBB"],
            "liquidity_bucket": ["liquid"],
        }
    )
    events = pd.DataFrame(
        {
            "event_id": ["t1", "t2", "t3"],
            "prediction_timestamp": pd.to_datetime(
                ["2026-01-02 10:00:00", "2026-01-02 10:10:00", "2026-01-02 10:20:00"]
            ),
            "bond_id": ["b1", "b1", "b1"],
            "issuer_id": ["iss1", "iss1", "iss1"],
            "side": [1, 1, -1],
            "price": [100.0, 100.1, 100.0],
            "notional": [100.0, 300.0, 100.0],
        }
    )
    rfqs = pd.DataFrame(
        {
            "rfq_id": ["r1", "r2", "r3"],
            "timestamp": pd.to_datetime(
                ["2026-01-02 09:55:00", "2026-01-02 10:05:00", "2026-01-02 10:15:00"]
            ),
            "bond_id": ["b1", "b1", "b1"],
            "issuer_id": ["iss1", "iss1", "iss1"],
            "side": [1, -1, 1],
            "size": [100.0, 300.0, 100.0],
            "event_kind": ["inquiry", "firm_up", "execution"],
            "response_count": [2, 1, 0],
            "number_of_dealers": [3, 3, 3],
            "responded": [True, True, False],
            "firmed_up": [False, True, False],
            "executed": [False, False, True],
            "response_latency_ms": [1000, 1200, 1500],
        }
    )
    quotes = pd.DataFrame(
        {
            "quote_id": ["q1", "q2"],
            "timestamp": pd.to_datetime(["2026-01-02 09:50:00", "2026-01-02 10:12:00"]),
            "bond_id": ["b1", "b1"],
            "bid": [99.8, 99.7],
            "ask": [100.2, 100.3],
            "mid": [100.0, 100.0],
            "spread": [0.4, 0.6],
            "source_disagreement": [0.02, 0.03],
        }
    )
    metadata = SourceMetadata(
        name="test",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1, customer sell = -1",
        price_units="price points",
        size_units="fixture units",
        point_in_time_safety="synthetic fixture",
    )
    return bundle_from_frames(bonds=bonds, events=events, rfqs=rfqs, quotes=quotes, metadata=metadata)

