import math
from pathlib import Path

import numpy as np
import pandas as pd

from mechanical_alpha.alphas import T1_triplet_momentum_reversal
from mechanical_alpha.cli import main as mechanical_alpha_main
from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.fx_cookbook.carry import blocked_carry, compute_fx_carry
from mechanical_alpha.fx_cookbook.cftc_reversal import blocked_cftc_reversal
from mechanical_alpha.fx_cookbook.coffee import blocked_coffee_dtcc
from mechanical_alpha.fx_cookbook.common import (
    apply_position_bounds,
    equal_weight_rank_halves,
    inverse_volatility_sign_weights,
    linear_rank_halves,
    project_beta_neutral,
    signal_proportional_weights,
    tranche_rebalance,
)
from mechanical_alpha.fx_cookbook.momentum import compute_total_return_momentum_signal
from mechanical_alpha.registry import standalone_alpha_index
from mechanical_alpha.schema import SideConvention
from mechanical_alpha.triplets.clocks import build_calendar_clock, build_event_clock, build_information_clock
from mechanical_alpha.triplets.inference import adjust_triplet_multiplicity, estimate_triplet_family, select_triplets
from mechanical_alpha.triplets.method import TripletMethodSpec, fit_triplet_method, score_triplet_method
from mechanical_alpha.triplets.panel import build_triplet_panel, sample_state_on_clock


def test_calendar_event_and_information_clocks_are_adapted() -> None:
    events = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:05", "2026-01-02 10:20"]),
            "notional": [10.0, 15.0, 40.0],
        }
    )

    calendar = build_calendar_clock("2026-01-02 10:00", "2026-01-02 10:20", "10min")
    event = build_event_clock(events, 2)
    information = build_information_clock(events, 25.0)

    assert list(calendar.timestamps) == list(pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:10", "2026-01-02 10:20"]))
    assert list(event.timestamps) == [pd.Timestamp("2026-01-02 10:05")]
    assert list(information.timestamps) == [pd.Timestamp("2026-01-02 10:05"), pd.Timestamp("2026-01-02 10:20")]


def test_information_clock_rejects_negative_activity() -> None:
    events = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-02 10:00"]), "notional": [-1.0]})
    try:
        build_information_clock(events, 1.0)
    except ValueError as exc:
        assert "nonnegative" in str(exc)
    else:
        raise AssertionError("negative information-clock activity should fail")


def test_triplet_estimation_detects_continuation_fixture() -> None:
    clock = build_calendar_clock("2026-01-02 10:00", "2026-01-02 11:30", "10min")
    state = pd.DataFrame(
        {
            "timestamp": clock.timestamps,
            "bond_id": ["b1"] * len(clock.timestamps),
            "price": np.arange(len(clock.timestamps), dtype=float) ** 2,
        }
    )
    sampled = sample_state_on_clock(state, clock)
    panel = build_triplet_panel(sampled, lags=(1,), horizons=(1,), target_type="clean_price")
    estimates = estimate_triplet_family(panel)

    assert estimates.loc[0, "rho"] > 0.99
    selected = select_triplets(adjust_triplet_multiplicity(estimates), alpha=1.0, min_obs=3)
    assert bool(selected.loc[0, "selected"])


def test_triplet_spread_implied_sign_is_duration_adjusted() -> None:
    sampled = pd.DataFrame(
        {
            "clock": ["c"] * 3,
            "clock_index": [0, 1, 2],
            "timestamp": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 10:10", "2026-01-02 10:20"]),
            "bond_id": ["b1"] * 3,
            "spread": [100.0, 110.0, 120.0],
            "duration": [5.0, 5.0, 5.0],
        }
    )
    panel = build_triplet_panel(sampled, lags=(1,), horizons=(1,), value_col="spread", duration_col="duration", target_type="spread_implied")

    assert panel.loc[0, "past_move"] == -50.0
    assert panel.loc[0, "future_move"] == -50.0


def test_future_mutation_does_not_change_train_fit_object() -> None:
    clock = build_calendar_clock("2026-01-02 10:00", "2026-01-02 11:30", "10min")
    state = pd.DataFrame(
        {
            "timestamp": clock.timestamps,
            "bond_id": ["b1"] * len(clock.timestamps),
            "price": np.arange(len(clock.timestamps), dtype=float) ** 2,
        }
    )
    train = state.iloc[:6].copy()
    fitted = fit_triplet_method(train, build_calendar_clock(train["timestamp"].min(), train["timestamp"].max(), "10min"), TripletMethodSpec(lags=(1,), horizons=(1,), alpha=1.0, min_obs=3))
    original_train_max = fitted.train_panel["future_move"].max()
    mutated = state.copy()
    mutated.loc[mutated.index[-1], "price"] = -999.0
    scored = score_triplet_method(mutated, clock, fitted)

    assert fitted.train_panel["future_move"].max() == original_train_max
    assert original_train_max == 9.0
    assert not scored.empty


def test_portfolio_primitives_handle_zero_denominators_and_neutrality() -> None:
    signal = pd.Series({"a": 2.0, "b": -1.0, "c": 0.5})
    vol = pd.Series({"a": 2.0, "b": 1.0, "c": 1.0})
    beta = pd.Series({"a": 1.0, "b": 1.0, "c": 1.0})

    inv = inverse_volatility_sign_weights(signal, vol)
    prop = signal_proportional_weights(signal, vol, vol_power=1.0)
    rank = equal_weight_rank_halves(signal)
    linear = linear_rank_halves(signal)
    neutral = project_beta_neutral(prop, beta)
    bounded = apply_position_bounds(prop, lower=-0.4, upper=0.4)

    assert math.isclose(inv.abs().sum(), 1.0)
    assert math.isclose(prop.abs().sum(), 1.0)
    assert math.isclose(rank.abs().sum(), 1.0)
    assert math.isclose(linear.sum(), 0.0, abs_tol=1e-12)
    assert math.isclose(float((neutral * beta).sum()), 0.0, abs_tol=1e-12)
    assert bounded.max() <= 0.4
    assert bounded.min() >= -0.4


def test_tranche_rebalance_averages_active_targets() -> None:
    targets = pd.DataFrame({"a": [1.0, 0.0, -1.0], "b": [-1.0, 0.0, 1.0]}, index=pd.RangeIndex(3))
    tranches = tranche_rebalance(targets, tranche_count=2)

    assert tranches.loc[0, "a"] == 0.5
    assert tranches.loc[1, "a"] == 0.5
    assert tranches.loc[2, "a"] == -0.5


def test_momentum_and_carry_source_literal_helpers() -> None:
    prices = pd.DataFrame({"a": [100.0, 101.0, 103.0]})
    momentum = compute_total_return_momentum_signal(prices, lookback=1)
    carry = compute_fx_carry(pd.DataFrame({"eurusd": [1.10]}), pd.DataFrame({"eurusd": [1.11]}), quote_orientation="base_per_quote")

    assert math.isclose(momentum.iloc[2, 0], 2.0 / 101.0)
    assert math.isclose(carry.iloc[0, 0], 1.11 / 1.10 - 1.0)


def test_blocked_strategies_preserve_source_decisions() -> None:
    assert blocked_carry().blocking_decisions == ("CARRY-001", "CARRY-002", "CARRY-003")
    assert blocked_coffee_dtcc().status == "BLOCKED_MISSING_DATA"
    assert blocked_cftc_reversal().blocking_decisions == ("CFTC-R-001",)


def test_triplet_alpha_registered_and_computable() -> None:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}
    bundle = _bundle()
    result = T1_triplet_momentum_reversal.compute(bundle, spec=TripletMethodSpec(lags=(1,), horizons=(1,), alpha=1.0, min_obs=3))

    assert index["T1"].module == "mechanical_alpha.alphas.T1_triplet_momentum_reversal"
    assert "t1_triplet_signal" in result.columns


def test_mechanical_alpha_cli_computes_selected_standalone_alpha(tmp_path: Path) -> None:
    scenario_root = _synthetic_scenario(tmp_path / "scenario=controlled_all")
    output = tmp_path / "features.parquet"

    assert mechanical_alpha_main(["compute", "--synthetic-root", str(scenario_root), "--alphas", "T1", "--output", str(output)]) == 0
    result = pd.read_parquet(output)

    assert result["alpha_id"].unique().tolist() == ["T1"]
    assert "t1_triplet_signal" in result.columns


def test_mechanical_alpha_cli_rejects_blocked_alpha(tmp_path: Path) -> None:
    scenario_root = _synthetic_scenario(tmp_path / "scenario=controlled_all")
    output = tmp_path / "features.parquet"

    try:
        mechanical_alpha_main(["compute", "--synthetic-root", str(scenario_root), "--alphas", "FX_CARRY", "--output", str(output)])
    except ValueError as exc:
        assert "not implemented" in str(exc)
    else:
        raise AssertionError("blocked cookbook alpha should not compute")


def _bundle() -> object:
    timestamps = pd.date_range("2026-01-02 10:00", periods=12, freq="10min")
    events = pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(len(timestamps))],
            "prediction_timestamp": timestamps,
            "bond_id": ["b1"] * len(timestamps),
            "issuer_id": ["i1"] * len(timestamps),
            "side": [1, -1] * 6,
            "price": np.arange(len(timestamps), dtype=float) + 100.0,
            "notional": [100.0] * len(timestamps),
        }
    )
    bonds = pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]})
    metadata = SourceMetadata(
        name="fixture",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1",
        price_units="price points",
        size_units="par",
        point_in_time_safety="fixture",
    )
    return bundle_from_frames(bonds=bonds, events=events, metadata=metadata)


def _synthetic_scenario(root: Path) -> Path:
    trade_root = root / "trades" / "year=2026" / "month=01"
    trade_root.mkdir(parents=True)
    timestamps = pd.date_range("2026-01-02 10:00", periods=12, freq="10min", tz="UTC")
    pd.DataFrame(
        {
            "synthetic_bond_id": ["b1"],
            "synthetic_issuer_id": ["i1"],
            "liquidity_bucket": ["liquid"],
        }
    ).to_parquet(root / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(len(timestamps))],
            "timestamp_utc": timestamps,
            "session_date": [str(ts.date()) for ts in timestamps],
            "synthetic_bond_id": ["b1"] * len(timestamps),
            "synthetic_issuer_id": ["i1"] * len(timestamps),
            "side": [1, -1] * 6,
            "notional": [100000.0] * len(timestamps),
            "price": np.arange(len(timestamps), dtype=float) ** 2 + 100.0,
            "is_interdealer": [False] * len(timestamps),
            "trade_type": ["customer"] * len(timestamps),
            "venue_bucket": ["synthetic"] * len(timestamps),
            "reporting_delay_ms": [0] * len(timestamps),
            "currency": ["USD"] * len(timestamps),
        }
    ).to_parquet(trade_root / "part-0000.parquet", index=False)
    return root
