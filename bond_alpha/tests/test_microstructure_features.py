import math

import pandas as pd

from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.features import compute_microstructure_features, diagnose_feature_frame, microstructure_feature_registry
from mechanical_alpha.schema import SideConvention


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


def test_a1_a2_use_only_prior_rows() -> None:
    features = compute_microstructure_features(_bundle(), event_windows=(5,), calendar_windows=("30m",))
    row = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:20:00")].iloc[0]

    assert math.isclose(row["a1_trace_side_valid_last_5_count_imbalance"], 1.0)
    assert row["a1_trace_side_valid_last_5_count"] == 2
    assert math.isclose(row["a2_trace_side_valid_last_5_raw_notional_imbalance"], 1.0)

    first_row = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:00:00")].iloc[0]
    assert first_row["a1_trace_side_valid_last_5_count_imbalance"] != first_row["a1_trace_side_valid_last_5_count_imbalance"]


def test_a4_last_side_and_switching_are_hand_calculated() -> None:
    features = compute_microstructure_features(_bundle(), event_windows=(5,), calendar_windows=("30m",))
    row = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:20:00")].iloc[0]

    assert row["a4_trace_last_side"] == 1
    assert row["a4_trace_same_side_run_length"] == 2
    assert row["a4_trace_last_5_fraction_same_as_last"] == 1.0
    assert math.isclose(row["a4_trace_last_5_switching_hazard"], 0.0)

    later = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:20:00")].iloc[0]
    assert later["a4_rfq_last_side"] == 1
    assert later["a4_rfq_same_side_run_length"] == 1
    assert math.isclose(later["a4_rfq_last_5_switching_hazard"], 1.0)


def test_a6_a16_optional_fields_are_point_in_time() -> None:
    features = compute_microstructure_features(_bundle(), event_windows=(5,), calendar_windows=("30m",))
    row = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:20:00")].iloc[0]

    assert math.isclose(row["a6_latest_composite_spread"], 0.6)
    assert math.isclose(row["a6_latest_composite_staleness_seconds"], 8 * 60)
    assert row["a16_latest_response_count"] == 0
    assert math.isclose(row["a16_latest_response_scarcity"], 1.0)
    assert math.isclose(row["a16_firmup_rate_last_25"], 1 / 3)
    assert math.isclose(row["a16_execution_rate_last_25"], 1 / 3)


def test_registry_and_diagnostics_cover_required_families() -> None:
    registry = {item.feature_id: item for item in microstructure_feature_registry()}
    assert {"A1", "A2", "A3", "A4", "A5", "A6", "A16"}.issubset(registry)
    assert registry["A2"].missing_policy
    assert registry["A6"].point_in_time_dependencies

    features = compute_microstructure_features(_bundle(), event_windows=(5,), calendar_windows=("30m",))
    diagnostics = diagnose_feature_frame(features, _bundle().bonds)
    assert "feature" in diagnostics.columns
    assert "non_null_rate" in diagnostics.columns
    assert diagnostics["feature"].str.contains("a1_trace_side_valid_last_5_count_imbalance").any()
