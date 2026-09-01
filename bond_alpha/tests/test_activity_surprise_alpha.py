import math

import numpy as np
import pandas as pd

from mechanical_alpha.alphas import A1_rfq_count_imbalance, A5_activity_surprise as A5
from mechanical_alpha.cli import main as alpha_cli
from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.data.synthetic import load_synthetic_bundle
from mechanical_alpha.features import compute_microstructure_features
from mechanical_alpha.schema import SideConvention


def test_calendar_window_excludes_future_and_current_event() -> None:
    bundle = _bundle()
    artifact = A5.fit(bundle, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    features = A5.score(bundle, artifact)
    row = _row(features, "b1", "2026-01-02 10:00:00")

    assert row["a5_trace_trace_trade_calendar_5h_observed_count"] == 1.0
    assert row["a5_trace_trace_trade_calendar_5h_notional_observed"] == 100.0


def test_trade_event_window_uses_exactly_last_n_trades() -> None:
    bundle = _bundle()
    artifact = A5.fit(bundle, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    features = A5.score(bundle, artifact)
    row = _row(features, "b1", "2026-01-09 10:00:00")

    assert row["a5_trace_trace_trade_event_5_observed_count"] == 5.0
    assert row["a5_trace_trace_trade_event_5_notional_observed"] == 2500.0


def test_training_only_fit_is_unchanged_by_test_period_mutation() -> None:
    base = _bundle()
    mutated_events = base.events.copy()
    mutated_events.loc[mutated_events["prediction_timestamp"] > pd.Timestamp("2026-01-07"), "notional"] = 99_000_000.0
    mutated = bundle_from_frames(bonds=base.bonds, events=mutated_events, rfqs=base.rfqs, metadata=base.metadata)

    first = A5.fit(base, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    second = A5.fit(mutated, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    label = A5.BaselineKey("trace", "trace_trade", "calendar", "5h", "notional").label()

    assert first.baselines[label].global_mean == second.baselines[label].global_mean


def test_dv01_cr01_and_issuer_activity_are_scored_separately() -> None:
    bundle = _bundle()
    artifact = A5.fit(bundle, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    features = A5.score(bundle, artifact)
    row = _row(features, "b1", "2026-01-02 10:00:00")

    assert row["a5_trace_trace_trade_calendar_5h_gross_dv01_observed"] == 1.0
    assert row["a5_trace_trace_trade_calendar_5h_signed_dv01_observed"] == 1.0
    assert row["a5_trace_trace_trade_calendar_5h_gross_cr01_observed"] == 2.0
    assert row["a5_trace_trace_trade_calendar_5h_signed_cr01_observed"] == 2.0
    assert row["a5_trace_issuer_trace_trade_calendar_5h_observed_count"] == 2.0
    assert math.isclose(row["a5_bond_vs_issuer_trace_trace_trade_calendar_5h_event_count_share"], 0.5)


def test_missing_cr01_is_flagged_not_replaced_with_notional() -> None:
    bundle = _bundle()
    events = bundle.events.drop(columns=["cr01"])
    no_cr01 = bundle_from_frames(bonds=bundle.bonds.drop(columns=["cr01"]), events=events, rfqs=bundle.rfqs, metadata=bundle.metadata)
    artifact = A5.fit(no_cr01, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    features = A5.score(no_cr01, artifact)
    row = _row(features, "b1", "2026-01-02 10:00:00")

    assert np.isnan(row["a5_trace_trace_trade_calendar_5h_gross_cr01_observed"])
    assert row["a5_trace_trace_trade_calendar_5h_gross_cr01_quality_flag"] == "missing_cr01"


def test_a5_runs_alone_and_inside_combined_microstructure_wrapper() -> None:
    bundle = _bundle()
    alone = A5.compute(bundle, calendar_windows=("5h",))
    combined = compute_microstructure_features(bundle, event_windows=(5,), calendar_windows=("5h",))
    another = A1_rfq_count_imbalance.compute(bundle, event_windows=(5,), calendar_windows=("5h",))

    assert "a5_trace_trace_trade_calendar_5h_standardized_count_surprise" in alone.columns
    assert "a5_trace_trace_trade_calendar_5h_standardized_count_surprise" in combined.columns
    assert "a1_trace_side_valid_last_5_count_imbalance" in another.columns


def test_config_mapping_controls_windows_and_static_risk_policy() -> None:
    config = A5.config_from_mapping(
        {
            "model_type": "auto",
            "calendar_windows": ["5h"],
            "rfq_event_windows": [5],
            "trade_event_windows": [5],
            "selected_windows": {"calendar_windows": ["5h"], "rfq_event_windows": [5], "trade_event_windows": [5]},
            "risk_measures": {
                "static_risk_unit": "per_1mm_notional",
                "rate_risk": {"allow_static_bond_fallback": True},
                "credit_risk": {"allow_static_bond_fallback": True},
            },
        }
    )

    assert config.model_type == "auto"
    assert config.allow_static_bond_dv01_fallback is True
    assert config.allow_static_bond_cr01_fallback is True
    assert config.static_risk_unit == "per_1mm_notional"


def test_static_risk_fallback_requires_explicit_policy() -> None:
    bundle = _bundle()
    events = bundle.events.drop(columns=["dv01", "cr01"])
    no_event_risk = bundle_from_frames(bonds=bundle.bonds, events=events, rfqs=bundle.rfqs, metadata=bundle.metadata)
    no_fallback = A5.score(no_event_risk, A5.fit(no_event_risk, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00")))
    fallback_config = A5.ActivitySurpriseConfig(
        calendar_windows=("5h",),
        trade_event_windows=(5,),
        selected_calendar_windows=("5h",),
        selected_trade_event_windows=(5,),
        minimum_observations=1,
        allow_static_bond_dv01_fallback=True,
        allow_static_bond_cr01_fallback=True,
        static_risk_unit="per_1mm_notional",
    )
    with_fallback = A5.score(
        no_event_risk,
        A5.fit(no_event_risk, config=fallback_config, train_end=pd.Timestamp("2026-01-07 10:00:00")),
    )

    assert no_fallback["a5_trace_trace_trade_calendar_5h_gross_dv01_observed"].isna().all()
    assert with_fallback["a5_trace_trace_trade_calendar_5h_gross_dv01_observed"].notna().any()


def test_ratio_surprise_uses_frozen_expected_ratio() -> None:
    bundle = _bundle()
    artifact = A5.fit(bundle, config=_config(), train_end=pd.Timestamp("2026-01-07 10:00:00"))
    features = A5.score(bundle, artifact)
    row = _row(features, "b1", "2026-01-05 10:00:00")

    assert "a5_ratios_calendar_5h_execution_to_inquiry_expected_ratio" in row
    assert "a5_ratios_calendar_5h_execution_to_inquiry_standardized_surprise" in row


def test_poisson_glm_selected_when_stable() -> None:
    bundle = _large_count_bundle()
    config = A5.ActivitySurpriseConfig(
        calendar_windows=("5h",),
        rfq_event_windows=(5,),
        trade_event_windows=(5,),
        selected_calendar_windows=("5h",),
        selected_rfq_event_windows=(5,),
        selected_trade_event_windows=(5,),
        minimum_observations=2,
        model_type="auto",
    )
    artifact = A5.fit(bundle, config=config, train_end=pd.Timestamp("2026-01-08 15:00:00"))
    label = A5.BaselineKey("trace", "trace_trade", "calendar", "5h", "event_count").label()

    assert artifact.baselines[label].model_type in {"poisson_glm", "hierarchical_empirical"}
    assert artifact.baselines[label].fit_note in {"poisson_glm_fit", "empirical_fallback"}


def test_synthetic_adapter_preserves_event_level_dv01_cr01(tmp_path) -> None:
    root = tmp_path / "scenario=controlled_all"
    (root / "trades/year=2026/month=01").mkdir(parents=True)
    pd.DataFrame({"synthetic_bond_id": ["b1"], "synthetic_issuer_id": ["iss1"]}).to_parquet(root / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": ["e1"],
            "timestamp_utc": [pd.Timestamp("2026-01-02 10:00", tz="UTC")],
            "session_date": ["2026-01-02"],
            "synthetic_bond_id": ["b1"],
            "synthetic_issuer_id": ["iss1"],
            "side": [1],
            "notional": [100.0],
            "price": [100.0],
            "is_interdealer": [False],
            "dv01": [12.3],
            "cr01": [45.6],
        }
    ).to_parquet(root / "trades/year=2026/month=01/part-0000.parquet", index=False)

    bundle = load_synthetic_bundle(root)

    assert bundle.events.loc[0, "dv01"] == 12.3
    assert bundle.events.loc[0, "cr01"] == 45.6


def test_cli_loads_a5_alpha_config(tmp_path) -> None:
    root = tmp_path / "scenario=controlled_all"
    output = tmp_path / "a5.parquet"
    config_path = tmp_path / "a5.yaml"
    _write_synthetic_root(root)
    config_path.write_text(
        """
alpha_id: A5
model_type: hierarchical_empirical
calendar_windows: [5h]
rfq_event_windows: [5]
trade_event_windows: [5]
selected_windows:
  calendar_windows: [5h]
  rfq_event_windows: [5]
  trade_event_windows: [5]
minimum_observations: 1
risk_measures:
  static_risk_unit:
  rate_risk:
    allow_static_bond_fallback: false
  credit_risk:
    allow_static_bond_fallback: false
"""
    )

    result = alpha_cli(["compute", "--synthetic-root", str(root), "--alphas", "A5", "--alpha-config", str(config_path), "--output", str(output)])

    assert result == 0
    columns = pd.read_parquet(output).columns
    assert "a5_trace_trace_trade_calendar_5h_gross_cr01_observed" in columns


def _row(features: pd.DataFrame, bond_id: str, timestamp: str) -> pd.Series:
    match = features[(features["bond_id"] == bond_id) & (features["prediction_timestamp"] == pd.Timestamp(timestamp))]
    assert len(match) == 1
    return match.iloc[0]


def _config() -> A5.ActivitySurpriseConfig:
    return A5.ActivitySurpriseConfig(
        calendar_windows=("5h",),
        rfq_event_windows=(5,),
        trade_event_windows=(5,),
        selected_calendar_windows=("5h",),
        selected_rfq_event_windows=(5,),
        selected_trade_event_windows=(5,),
        minimum_observations=1,
    )


def _bundle() -> object:
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1", "b2"],
            "issuer_id": ["iss1", "iss1"],
            "sector": ["industrial", "industrial"],
            "rating": ["BBB", "BBB"],
            "rating_bucket": ["BBB", "BBB"],
            "maturity_bucket": ["5y", "10y"],
            "liquidity_bucket": ["liquid", "illiquid"],
            "dv01": [10.0, 20.0],
            "cr01": [15.0, 25.0],
        }
    )
    events = pd.DataFrame(
        {
            "event_id": [f"t{i}" for i in range(10)],
            "prediction_timestamp": pd.to_datetime(
                [
                    "2026-01-02 09:00:00",
                    "2026-01-02 09:30:00",
                    "2026-01-02 10:00:00",
                    "2026-01-02 10:30:00",
                    "2026-01-05 10:00:00",
                    "2026-01-06 10:00:00",
                    "2026-01-07 10:00:00",
                    "2026-01-08 10:00:00",
                    "2026-01-09 10:00:00",
                    "2026-01-09 10:30:00",
                ]
            ),
            "bond_id": ["b1", "b2", "b1", "b1", "b1", "b1", "b1", "b1", "b1", "b1"],
            "issuer_id": ["iss1"] * 10,
            "side": [1, -1, 1, -1, 1, -1, 1, -1, 1, -1],
            "price": [100.0] * 10,
            "notional": [100.0, 50.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0],
            "dv01": [1.0, 0.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            "cr01": [2.0, 1.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0],
        }
    )
    rfqs = pd.DataFrame(
        {
            "rfq_id": [f"r{i}" for i in range(5)],
            "timestamp": pd.to_datetime(
                [
                    "2026-01-02 08:45:00",
                    "2026-01-02 09:15:00",
                    "2026-01-02 09:45:00",
                    "2026-01-02 10:15:00",
                    "2026-01-05 09:45:00",
                ]
            ),
            "bond_id": ["b1", "b1", "b2", "b1", "b1"],
            "issuer_id": ["iss1"] * 5,
            "side": [1, -1, 1, 1, -1],
            "size": [100.0, 200.0, 50.0, 300.0, 400.0],
            "dv01": [1.0, 2.0, 0.5, 3.0, 4.0],
            "cr01": [2.0, 4.0, 1.0, 6.0, 8.0],
            "event_kind": ["inquiry", "firm_up", "inquiry", "execution", "inquiry"],
        }
    )
    metadata = SourceMetadata(
        name="a5_test",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1, customer sell = -1",
        price_units="price points",
        size_units="fixture notional",
        point_in_time_safety="synthetic fixture",
    )
    return bundle_from_frames(bonds=bonds, events=events, rfqs=rfqs, metadata=metadata)


def _large_count_bundle() -> object:
    timestamps = pd.date_range("2026-01-02 09:00:00", periods=80, freq="30min")
    events = pd.DataFrame(
        {
            "event_id": [f"g{i}" for i in range(len(timestamps))],
            "prediction_timestamp": timestamps,
            "bond_id": ["b1" if i % 2 == 0 else "b2" for i in range(len(timestamps))],
            "issuer_id": ["iss1"] * len(timestamps),
            "side": [1 if i % 3 else -1 for i in range(len(timestamps))],
            "price": [100.0] * len(timestamps),
            "notional": [100.0 + i for i in range(len(timestamps))],
            "dv01": [1.0 + i / 10.0 for i in range(len(timestamps))],
            "cr01": [2.0 + i / 10.0 for i in range(len(timestamps))],
        }
    )
    bonds = pd.DataFrame(
        {
            "bond_id": ["b1", "b2"],
            "issuer_id": ["iss1", "iss1"],
            "sector": ["industrial", "industrial"],
            "rating_bucket": ["BBB", "BBB"],
            "maturity_bucket": ["5y", "10y"],
            "liquidity_bucket": ["liquid", "illiquid"],
        }
    )
    metadata = SourceMetadata("a5_glm", SideConvention.CUSTOMER, "customer buy = +1", "price", "notional", "fixture")
    return bundle_from_frames(bonds=bonds, events=events, metadata=metadata)


def _write_synthetic_root(root: object) -> None:
    root = pd.io.common.stringify_path(root)
    from pathlib import Path

    path = Path(root)
    (path / "trades/year=2026/month=01").mkdir(parents=True)
    pd.DataFrame(
        {
            "synthetic_bond_id": ["b1", "b2"],
            "synthetic_issuer_id": ["iss1", "iss1"],
            "liquidity_bucket": ["liquid", "illiquid"],
            "rating_bucket": ["BBB", "BBB"],
            "sector": ["industrial", "industrial"],
            "maturity_bucket": ["5y", "10y"],
        }
    ).to_parquet(path / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(8)],
            "timestamp_utc": pd.date_range("2026-01-02 09:00", periods=8, freq="30min", tz="UTC"),
            "session_date": ["2026-01-02"] * 8,
            "synthetic_bond_id": ["b1"] * 5 + ["b2"] * 3,
            "synthetic_issuer_id": ["iss1"] * 8,
            "side": [1, -1] * 4,
            "notional": [100.0 + idx for idx in range(8)],
            "price": [100.0] * 8,
            "is_interdealer": [False] * 8,
            "dv01": [1.0 + idx for idx in range(8)],
            "cr01": [2.0 + idx for idx in range(8)],
        }
    ).to_parquet(path / "trades/year=2026/month=01/part-0000.parquet", index=False)
