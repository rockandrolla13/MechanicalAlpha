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
            "cr01": [10.0, 30.0, 10.0],
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
            "cr01": [10.0, 30.0, 10.0],
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


def test_a1_a2_fit_asymmetric_cr01_weights_from_training_only() -> None:
    from mechanical_alpha.alphas import A1_rfq_count_imbalance as A1
    from mechanical_alpha.alphas import A2_rfq_notional_imbalance as A2

    bundle = _drifted_cr01_bundle()
    train_end = pd.Timestamp("2026-01-02 09:45:00")
    a1_config = A1.CountImbalanceConfig(event_windows=(5,), calendar_windows=("5h",), risk_measures=("count", "cr01"))
    a2_config = A2.RiskImbalanceConfig(event_windows=(5,), calendar_windows=("5h",), risk_measures=("cr01",), variants=("raw",))

    a1_artifact = A1.fit(bundle, config=a1_config, train_end=train_end)
    a2_artifact = A2.fit(bundle, config=a2_config, train_end=train_end)
    a1 = A1.score(bundle, a1_artifact)
    a2 = A2.score(bundle, a2_artifact)

    row_time = pd.Timestamp("2026-01-02 10:00:00")
    a1_row = a1[a1["prediction_timestamp"] == row_time].iloc[0]
    a2_row = a2[a2["prediction_timestamp"] == row_time].iloc[0]

    assert math.isclose(a1_row["a1_trace_side_valid_last_5_count_weighted_imbalance"], 0.0, abs_tol=1e-12)
    assert math.isclose(a1_row["a1_trace_side_valid_last_5_cr01_weighted_imbalance"], 0.0, abs_tol=1e-12)
    assert math.isclose(a2_row["a2_trace_side_valid_last_5_cr01_raw_imbalance"], 0.0, abs_tol=1e-12)
    assert a1_row["a1_trace_side_valid_last_5_count_buy_weight"] < a1_row["a1_trace_side_valid_last_5_count_sell_weight"]
    assert a2_row["a2_trace_side_valid_last_5_cr01_raw_buy_weight"] < a2_row["a2_trace_side_valid_last_5_cr01_raw_sell_weight"]

    mutated = _drifted_cr01_bundle()
    mutated.events.loc[4, "side"] = 1
    mutated.events.loc[4, "cr01"] = 1000.0
    mutated_artifact = A1.fit(mutated, config=a1_config, train_end=train_end)
    assert a1_artifact.weights == mutated_artifact.weights


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


def test_a3_fits_days_scale_baseline_from_training_only() -> None:
    from mechanical_alpha.alphas import A3_buy_sell_intensity as A3

    bundle = _intensity_bundle()
    config = A3.IntensityConfig(half_life_candidates=("1d", "5d", "20d"), forecast_window="1d", minimum_observations=3)
    train_end = pd.Timestamp("2026-01-08 09:00:00")
    artifact = A3.fit(bundle, config=config, train_end=train_end)

    assert artifact.fitted["rfq:1:cr01"].selected_half_life in {"1d", "5d", "20d"}
    assert artifact.fitted["rfq:1:cr01"].baseline_intensity_per_second > 0
    assert artifact.fitted["rfq:-1:cr01"].baseline_intensity_per_second > 0
    assert artifact.fitted["trace:1"].selected_half_life in {"1d", "5d", "20d"}
    assert artifact.fitted["trace:1"].baseline_intensity_per_second > 0
    assert artifact.fitted["trace:-1"].baseline_intensity_per_second > 0

    features = A3.score(bundle, artifact)
    scored = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-09 09:00:00")].iloc[0]
    assert "a3_trace_fitted_buy_expected_intensity" in features.columns
    assert "a3_rfq_fitted_cr01_buy_expected_intensity" in features.columns
    assert "a3_rfq_fitted_cr01_intensity_surprise_difference" in features.columns
    assert "a3_trace_fitted_intensity_surprise_difference" in features.columns
    assert scored["a3_rfq_fitted_cr01_buy_half_life"] in {"1d", "5d", "20d"}

    mutated = _intensity_bundle()
    mutated.rfqs.loc[len(mutated.rfqs) - 1, "side"] = 1
    mutated.rfqs.loc[len(mutated.rfqs) - 1, "timestamp"] = pd.Timestamp("2026-02-01 09:00:00")
    mutated.rfqs.loc[len(mutated.rfqs) - 1, "cr01"] = 10_000.0
    mutated_artifact = A3.fit(mutated, config=config, train_end=train_end)
    assert artifact.fitted == mutated_artifact.fitted


def test_a6_a16_optional_fields_are_point_in_time() -> None:
    features = compute_microstructure_features(_bundle(), event_windows=(5,), calendar_windows=("30m",))
    row = features[features["prediction_timestamp"] == pd.Timestamp("2026-01-02 10:20:00")].iloc[0]

    assert math.isclose(row["a6_latest_composite_spread"], 0.6)
    assert math.isclose(row["a6_latest_composite_staleness_seconds"], 8 * 60)
    assert row["a16_latest_response_count"] == 0
    assert math.isclose(row["a16_latest_response_scarcity"], 1.0)
    assert math.isclose(row["a16_firmup_rate_last_25"], 1 / 3)
    assert math.isclose(row["a16_execution_rate_last_25"], 1 / 3)


def test_a6_a16_emit_fast_and_slow_horizon_features() -> None:
    from mechanical_alpha.alphas import A16_rfq_scarcity_disagreement as A16
    from mechanical_alpha.alphas import A6_spread_conditioned_flow as A6

    bundle = _bundle()
    a6 = A6.compute(bundle)
    a16 = A16.compute(bundle)

    assert "a6_fast_calendar_1d_notional_flow_pressure" in a6.columns
    assert "a6_fast_calendar_3d_cr01_flow_pressure" in a6.columns
    assert "a6_slow_calendar_40d_notional_flow_x_spread" in a6.columns
    assert "a6_slow_trade_last_50_cr01_quality_flag" in a6.columns
    assert "a16_fast_calendar_1d_no_response_rate" in a16.columns
    assert "a16_fast_event_last_10_firmup_rate" in a16.columns
    assert "a16_slow_calendar_120d_execution_rate" in a16.columns
    assert "a16_slow_event_last_50_mean_response_count" in a16.columns


def test_a6_fits_simple_model_from_training_only() -> None:
    from mechanical_alpha.alphas import A6_spread_conditioned_flow as A6

    bundle = _fitted_a6_bundle()
    config = A6.SpreadConditionedFlowConfig(
        fast_calendar_windows=("1d",),
        slow_calendar_windows=("5d",),
        fast_trade_windows=(5,),
        slow_trade_windows=(25,),
        minimum_fit_observations=3,
        target_columns=("future_clean_price_move",),
    )
    train_end = pd.Timestamp("2026-01-08 10:00:00")

    artifact = A6.fit(bundle, config=config, train_end=train_end)
    scored = A6.score(bundle, artifact)

    assert artifact.models["future_clean_price_move"].model_type == "ridge"
    assert artifact.models["future_clean_price_move"].train_observations >= 3
    assert "a6_fitted_future_clean_price_move_score" in scored.columns

    mutated = _fitted_a6_bundle()
    mutated.events.loc[mutated.events["prediction_timestamp"] > train_end, "future_clean_price_move"] = 10_000.0
    mutated_artifact = A6.fit(mutated, config=config, train_end=train_end)
    assert artifact.models["future_clean_price_move"] == mutated_artifact.models["future_clean_price_move"]


def test_a16_fits_simple_liquidity_model_from_training_only() -> None:
    from mechanical_alpha.alphas import A16_rfq_scarcity_disagreement as A16

    bundle = _fitted_a16_bundle()
    config = A16.RFQScarcityConfig(
        fast_calendar_windows=("1d",),
        slow_calendar_windows=("5d",),
        fast_rfq_windows=(5,),
        slow_rfq_windows=(25,),
        minimum_fit_observations=3,
        target_columns=("executed",),
    )
    train_end = pd.Timestamp("2026-01-09 10:00:00")

    artifact = A16.fit(bundle, config=config, train_end=train_end)
    scored = A16.score(bundle, artifact)

    assert artifact.models["executed"].model_type in {"logistic_regression", "constant_fallback"}
    assert artifact.models["executed"].train_observations >= 3
    assert "a16_fitted_probability_executed" in scored.columns
    assert scored["a16_fitted_probability_executed"].dropna().between(0.0, 1.0).all()

    mutated = _fitted_a16_bundle()
    mutated.rfqs.loc[mutated.rfqs["timestamp"] > train_end, "executed"] = True
    mutated_artifact = A16.fit(mutated, config=config, train_end=train_end)
    assert artifact.models["executed"] == mutated_artifact.models["executed"]


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


def _drifted_cr01_bundle() -> object:
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "issuer_id": ["iss1"],
            "sector": ["industrial"],
            "rating": ["BBB"],
            "liquidity_bucket": ["liquid"],
        }
    )
    timestamps = pd.to_datetime(
        [
            "2026-01-02 09:00:00",
            "2026-01-02 09:10:00",
            "2026-01-02 09:20:00",
            "2026-01-02 09:30:00",
            "2026-01-02 10:00:00",
        ]
    )
    events = pd.DataFrame(
        {
            "event_id": [f"t{i}" for i in range(5)],
            "prediction_timestamp": timestamps,
            "bond_id": ["b1"] * 5,
            "issuer_id": ["iss1"] * 5,
            "side": [1, 1, 1, -1, -1],
            "price": [100.0, 100.1, 100.2, 100.1, 100.0],
            "notional": [100.0, 100.0, 100.0, 100.0, 500.0],
            "cr01": [10.0, 10.0, 10.0, 10.0, 100.0],
        }
    )
    metadata = SourceMetadata(
        name="drifted",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1, customer sell = -1",
        price_units="price points",
        size_units="fixture units",
        point_in_time_safety="synthetic fixture",
    )
    return bundle_from_frames(bonds=bonds, events=events, metadata=metadata)


def _intensity_bundle() -> object:
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "issuer_id": ["iss1"],
            "sector": ["industrial"],
            "rating": ["BBB"],
            "liquidity_bucket": ["liquid"],
        }
    )
    dates = pd.bdate_range("2026-01-01", periods=8)
    rows = []
    for idx, date in enumerate(dates):
        rows.append(
            {
                "event_id": f"buy_{idx}",
                "prediction_timestamp": date + pd.Timedelta(hours=9),
                "bond_id": "b1",
                "issuer_id": "iss1",
                "side": 1,
                "price": 100.0,
                "notional": 100.0,
                "cr01": 10.0 + idx,
            }
        )
        if idx % 2 == 0:
            rows.append(
                {
                    "event_id": f"sell_{idx}",
                    "prediction_timestamp": date + pd.Timedelta(hours=10),
                    "bond_id": "b1",
                    "issuer_id": "iss1",
                    "side": -1,
                    "price": 100.0,
                    "notional": 100.0,
                    "cr01": 20.0 + idx,
                }
            )
    rfqs = pd.DataFrame(
        {
            "rfq_id": [f"r{i}" for i in range(len(rows))],
            "timestamp": [row["prediction_timestamp"] - pd.Timedelta(minutes=5) for row in rows],
            "bond_id": [row["bond_id"] for row in rows],
            "issuer_id": [row["issuer_id"] for row in rows],
            "side": [row["side"] for row in rows],
            "size": [row["notional"] for row in rows],
            "cr01": [row["cr01"] for row in rows],
            "event_kind": ["inquiry"] * len(rows),
        }
    )
    metadata = SourceMetadata(
        name="intensity",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1, customer sell = -1",
        price_units="price points",
        size_units="fixture units",
        point_in_time_safety="synthetic fixture",
    )
    return bundle_from_frames(bonds=bonds, events=pd.DataFrame(rows), rfqs=rfqs, metadata=metadata)


def _fitted_a6_bundle() -> object:
    dates = pd.bdate_range("2026-01-02", periods=9)
    events = pd.DataFrame(
        {
            "event_id": [f"a6_{idx}" for idx in range(len(dates))],
            "prediction_timestamp": [date + pd.Timedelta(hours=10) for date in dates],
            "bond_id": ["b1"] * len(dates),
            "issuer_id": ["iss1"] * len(dates),
            "side": [1, -1, 1, -1, 1, -1, 1, -1, 1],
            "price": [100.0] * len(dates),
            "notional": [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0],
            "cr01": [10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0],
            "future_clean_price_move": [0.01, -0.02, 0.02, -0.03, 0.03, -0.04, 0.04, -0.05, 0.05],
        }
    )
    quotes = pd.DataFrame(
        {
            "quote_id": [f"q{idx}" for idx in range(len(dates))],
            "timestamp": [date + pd.Timedelta(hours=9) for date in dates],
            "bond_id": ["b1"] * len(dates),
            "bid": [99.8] * len(dates),
            "ask": [100.2 + idx / 100.0 for idx in range(len(dates))],
            "mid": [100.0] * len(dates),
            "spread": [0.4 + idx / 100.0 for idx in range(len(dates))],
            "source_disagreement": [0.01 + idx / 1000.0 for idx in range(len(dates))],
        }
    )
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "issuer_id": ["iss1"],
            "sector": ["industrial"],
            "rating": ["BBB"],
            "liquidity_bucket": ["liquid"],
        }
    )
    metadata = SourceMetadata("a6_fit", SideConvention.CUSTOMER, "customer buy = +1", "price", "notional", "fixture")
    return bundle_from_frames(bonds=bonds, events=events, quotes=quotes, metadata=metadata)


def _fitted_a16_bundle() -> object:
    dates = pd.bdate_range("2026-01-02", periods=10)
    rfqs = pd.DataFrame(
        {
            "rfq_id": [f"a16_{idx}" for idx in range(len(dates))],
            "timestamp": [date + pd.Timedelta(hours=10) for date in dates],
            "bond_id": ["b1"] * len(dates),
            "issuer_id": ["iss1"] * len(dates),
            "side": [1, -1] * 5,
            "size": [100.0 + idx for idx in range(len(dates))],
            "event_kind": ["inquiry"] * len(dates),
            "response_count": [1, 2, 1, 3, 0, 2, 1, 3, 0, 2],
            "number_of_dealers": [3] * len(dates),
            "quote_dispersion": [0.02, 0.01, 0.03, 0.01, 0.05, 0.02, 0.03, 0.01, 0.04, 0.02],
            "response_latency_ms": [1000, 900, 1200, 800, 1500, 1100, 1300, 700, 1600, 1000],
            "responded": [True, True, True, True, False, True, True, True, False, True],
            "firmed_up": [False, True, False, True, False, True, False, True, False, True],
            "executed": [False, True, False, True, False, True, False, True, False, True],
        }
    )
    events = pd.DataFrame(
        {
            "event_id": [f"e{idx}" for idx in range(len(dates))],
            "prediction_timestamp": [date + pd.Timedelta(hours=10) for date in dates],
            "bond_id": ["b1"] * len(dates),
            "issuer_id": ["iss1"] * len(dates),
            "side": [1, -1] * 5,
            "price": [100.0] * len(dates),
            "notional": [100.0] * len(dates),
        }
    )
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1"],
            "issuer_id": ["iss1"],
            "sector": ["industrial"],
            "rating": ["BBB"],
            "liquidity_bucket": ["liquid"],
        }
    )
    metadata = SourceMetadata("a16_fit", SideConvention.CUSTOMER, "customer buy = +1", "price", "notional", "fixture")
    return bundle_from_frames(bonds=bonds, events=events, rfqs=rfqs, metadata=metadata)
