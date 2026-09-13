import math

import pandas as pd

from mechanical_alpha.portfolio import PortfolioConfig, construct_target_positions, portfolio_from_signals


def test_rank_long_short_weights_top_half_long_bottom_half_short() -> None:
    signals = pd.DataFrame(
        {
            "prediction_timestamp": pd.Timestamp("2026-01-02 10:00"),
            "bond_id": ["B1", "B2", "B3", "B4"],
            "signal": [-2.0, -1.0, 1.0, 3.0],
        }
    )

    result = construct_target_positions(signals)

    weights = dict(zip(result["bond_id"], result["target_weight"], strict=True))
    assert weights["B1"] < 0
    assert weights["B2"] < 0
    assert weights["B3"] > 0
    assert weights["B4"] > 0
    assert math.isclose(result["target_exposure"].abs().sum(), 1.0)


def test_signal_proportional_weights_preserve_signal_direction() -> None:
    signals = pd.DataFrame({"bond_id": ["B1", "B2", "B3"], "signal": [2.0, -1.0, 0.0]})

    result = portfolio_from_signals(signals, weight_method="signal_proportional", gross_target=3.0)

    exposures = dict(zip(result["bond_id"], result["target_exposure"], strict=True))
    assert math.isclose(exposures["B1"], 2.0)
    assert math.isclose(exposures["B2"], -1.0)
    assert math.isclose(exposures["B3"], 0.0)


def test_cr01_scaling_converts_exposure_to_position_units() -> None:
    signals = pd.DataFrame(
        {
            "prediction_timestamp": [pd.Timestamp("2026-01-02")] * 2,
            "bond_id": ["B1", "B2"],
            "signal": [1.0, -1.0],
            "cr01": [100.0, 50.0],
        }
    )

    result = construct_target_positions(
        signals,
        PortfolioConfig(weight_method="signal_proportional", risk_unit="cr01", gross_target=300.0),
    )

    positions = dict(zip(result["bond_id"], result["target_position"], strict=True))
    assert math.isclose(positions["B1"], 1.5)
    assert math.isclose(positions["B2"], -3.0)
    assert math.isclose(result["target_exposure"].abs().sum(), 300.0)


def test_position_caps_are_applied_before_realized_gross_is_reported() -> None:
    signals = pd.DataFrame(
        {
            "bond_id": ["B1", "B2"],
            "signal": [10.0, -10.0],
            "dv01": [100.0, 100.0],
        }
    )

    result = construct_target_positions(
        signals,
        PortfolioConfig(
            weight_method="signal_proportional",
            risk_unit="dv01",
            gross_target=1_000.0,
            max_abs_position=2.0,
        ),
    )

    assert result["target_position"].abs().max() <= 2.0
    assert math.isclose(result["realized_gross_exposure"].iloc[0], 400.0)


def test_invalid_or_missing_signals_return_flat_positions() -> None:
    signals = pd.DataFrame({"bond_id": ["B1", "B2"], "signal": [float("nan"), float("nan")]})

    result = construct_target_positions(signals)

    assert result["target_position"].eq(0.0).all()
    assert result["portfolio_quality_flag"].eq("flat_no_valid_signals").all()
