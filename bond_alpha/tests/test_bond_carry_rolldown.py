import math

import numpy as np
import pandas as pd

from mechanical_alpha.alphas import BOND_carry_rolldown
from mechanical_alpha.cli import main as mechanical_alpha_main
from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.fx_cookbook.carry import (
    ParAdjustedCarryInputs,
    ParAdjustedCurveConfig,
    compute_par_adjusted_carry_rolldown,
)
from mechanical_alpha.registry import standalone_alpha_index
from mechanical_alpha.schema import SideConvention


def test_par_adjusted_carry_rolldown_matches_hand_calculation() -> None:
    result = compute_par_adjusted_carry_rolldown(
        ParAdjustedCarryInputs(
            par_adjusted_spread=120.0,
            model_par_spread=100.0,
            rolled_model_par_spread=90.0,
            risky_pv01=5.0,
            rolled_risky_pv01=4.9,
            coupon_minus_riskfree=2.0,
        ),
        ParAdjustedCurveConfig(horizon_years=1.0 / 252.0),
    )

    s_bar = 0.012
    s_hat = 0.010
    s_rolled = 0.009
    c_prime = 0.02
    carry = c_prime / 252.0 + (s_bar - c_prime) * (5.0 - 4.9)
    rolldown = (s_hat - s_rolled) * 4.9
    rv = (s_bar - s_hat) * 4.9

    assert math.isclose(result["carry"], carry * 100.0)
    assert math.isclose(result["rolldown"], rolldown * 100.0)
    assert math.isclose(result["relative_value"], rv * 100.0)
    assert math.isclose(result["total_return"], (carry + rolldown + rv) * 100.0)


def test_bond_carry_alpha_uses_latest_published_curve_only() -> None:
    bundle = _bundle_with_curve()

    result = BOND_carry_rolldown.compute(bundle, config=BOND_carry_rolldown.BondCarryRolldownConfig(horizons=("1d",)))

    assert result.loc[0, "bond_carry_rolldown_1d_quality_flag"] == "ok"
    assert result.loc[0, "bond_carry_rolldown_1d_model_par_spread"] == 100.0
    assert result.loc[0, "bond_carry_rolldown_1d_rolled_model_par_spread"] < 100.0
    assert result.loc[0, "bond_carry_rolldown_1d_relative_value"] > 0.0


def test_future_published_curve_does_not_change_historical_signal() -> None:
    bundle = _bundle_with_curve()
    baseline = BOND_carry_rolldown.compute(bundle, config=BOND_carry_rolldown.BondCarryRolldownConfig(horizons=("1d",)))
    mutated = bundle.external_factors.copy()
    mutated.loc[len(mutated)] = {
        "timestamp": pd.Timestamp("2026-01-02 09:45"),
        "publication_timestamp": pd.Timestamp("2026-01-02 10:30"),
        "factor_id": "par_adjusted_spread_curve",
        "value": 0.0,
        "bond_id": "b1",
        "issuer_id": "i1",
        "curve_id": "i1_curve",
        "tenor_years": 5.0,
        "years_to_maturity": 5.0,
        "par_adjusted_spread": 500.0,
        "model_par_spread": 500.0,
        "risky_pv01": 9.0,
        "coupon_minus_riskfree": 10.0,
    }
    changed = bundle_from_frames(
        bonds=bundle.bonds,
        events=bundle.events,
        metadata=bundle.metadata,
        external_factors=mutated,
    )
    scored = BOND_carry_rolldown.compute(changed, config=BOND_carry_rolldown.BondCarryRolldownConfig(horizons=("1d",)))

    assert scored.loc[0, "bond_carry_rolldown_1d_total_return"] == baseline.loc[0, "bond_carry_rolldown_1d_total_return"]


def test_missing_curve_outputs_nan_with_quality_flag() -> None:
    bundle = bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]}),
        events=_events(),
        metadata=_metadata(),
    )

    result = BOND_carry_rolldown.compute(bundle, config=BOND_carry_rolldown.BondCarryRolldownConfig(horizons=("1d",)))

    assert np.isnan(result.loc[0, "bond_carry_rolldown_1d_total_return"])
    assert result.loc[0, "bond_carry_rolldown_1d_quality_flag"] == "missing_par_adjusted_curve"


def test_bond_carry_alpha_registered() -> None:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}

    assert index["BOND_CARRY_ROLLDOWN"].module == "mechanical_alpha.alphas.BOND_carry_rolldown"
    assert index["BOND_CARRY_ROLLDOWN"].status == "implemented"


def test_cli_computes_bond_carry_alpha_with_external_curve(tmp_path) -> None:
    scenario_root = _synthetic_scenario(tmp_path / "scenario=controlled_all")
    _curve().to_parquet(scenario_root / "external_factors.parquet", index=False)
    output = tmp_path / "features.parquet"

    result = mechanical_alpha_main(
        [
            "compute",
            "--synthetic-root",
            str(scenario_root),
            "--alphas",
            "BOND_CARRY_ROLLDOWN",
            "--alpha-config",
            "configs/alphas/bond_carry_rolldown.yaml",
            "--output",
            str(output),
        ]
    )
    features = pd.read_parquet(output)

    assert result == 0
    assert features["alpha_id"].unique().tolist() == ["BOND_CARRY_ROLLDOWN"]
    assert "bond_carry_rolldown_1d_total_return" in features.columns


def _bundle_with_curve() -> object:
    return bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]}),
        events=_events(),
        metadata=_metadata(),
        external_factors=_curve(),
    )


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["e1"],
            "prediction_timestamp": [pd.Timestamp("2026-01-02 10:00")],
            "bond_id": ["b1"],
            "issuer_id": ["i1"],
            "side": [1],
            "price": [100.0],
            "notional": [1_000_000.0],
        }
    )


def _curve() -> pd.DataFrame:
    rows = []
    for tenor, spread, rpv01 in [(2.0, 80.0, 1.9), (5.0, 100.0, 4.8), (10.0, 140.0, 8.0)]:
        rows.append(
            {
                "timestamp": pd.Timestamp("2026-01-02 09:00"),
                "publication_timestamp": pd.Timestamp("2026-01-02 09:05"),
                "factor_id": "par_adjusted_spread_curve",
                "value": spread,
                "bond_id": "b1",
                "issuer_id": "i1",
                "curve_id": "i1_curve",
                "tenor_years": tenor,
                "years_to_maturity": 5.0,
                "par_adjusted_spread": 125.0,
                "model_par_spread": spread,
                "risky_pv01": rpv01,
                "coupon_minus_riskfree": 2.0,
            }
        )
    return pd.DataFrame(rows)


def _metadata() -> SourceMetadata:
    return SourceMetadata(
        name="fixture",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="customer buy = +1",
        price_units="price points",
        size_units="par",
        point_in_time_safety="fixture",
    )


def _synthetic_scenario(root) -> object:
    trade_root = root / "trades" / "year=2026" / "month=01"
    trade_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "synthetic_bond_id": ["b1"],
            "synthetic_issuer_id": ["i1"],
            "liquidity_bucket": ["liquid"],
        }
    ).to_parquet(root / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": ["e1"],
            "timestamp_utc": [pd.Timestamp("2026-01-02 10:00", tz="UTC")],
            "session_date": ["2026-01-02"],
            "synthetic_bond_id": ["b1"],
            "synthetic_issuer_id": ["i1"],
            "side": [1],
            "notional": [1_000_000.0],
            "price": [100.0],
            "is_interdealer": [False],
            "trade_type": ["customer"],
            "venue_bucket": ["synthetic"],
            "reporting_delay_ms": [0],
            "currency": ["USD"],
        }
    ).to_parquet(trade_root / "part-0000.parquet", index=False)
    return root
