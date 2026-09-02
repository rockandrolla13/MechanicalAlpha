import numpy as np
import pandas as pd
import yaml
from pathlib import Path

from mechanical_alpha.alphas import ETF_options_positioning
from mechanical_alpha.contracts import SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.fx_cookbook.coffee import filter_coffee_options, normalize_option_direction
from mechanical_alpha.registry import standalone_alpha_index
from mechanical_alpha.schema import SideConvention


def test_options_direction_maps_calls_positive_puts_negative() -> None:
    normalized = normalize_option_direction(_options())

    assert normalized.loc[0, "directional_option_notional"] == 100.0
    assert normalized.loc[1, "directional_option_notional"] == -40.0


def test_options_filter_is_point_in_time_and_excludes_expiring_today() -> None:
    options = _options()
    options.loc[2, "publication_timestamp"] = pd.Timestamp("2026-01-03 12:00")
    options.loc[3, "expiry_date"] = pd.Timestamp("2026-01-03")

    filtered = filter_coffee_options(options, asof=pd.Timestamp("2026-01-03 10:00"))

    assert filtered["option_notional"].tolist() == [100.0, 40.0]


def test_etf_options_alpha_computes_signal_from_external_factors() -> None:
    bundle = _bundle(_options())

    result = ETF_options_positioning.compute(
        bundle,
        config=ETF_options_positioning.ETFOptionsAlphaConfig(signal_window="28D", min_vol_observations=1),
    )

    assert "etf_options_positioning_28d_signal" in result.columns
    assert np.isfinite(result.loc[0, "etf_options_positioning_28d_observed_imbalance"])
    assert result.loc[0, "etf_options_positioning_28d_quality_flag"] == "ok"


def test_etf_options_alpha_computes_all_component_signals() -> None:
    bundle = _bundle(_options())

    result = ETF_options_positioning.compute(
        bundle,
        config=ETF_options_positioning.ETFOptionsAlphaConfig(signal_windows=("5D",), min_vol_observations=1),
    )

    assert result.loc[0, "etf_options_5d_oi_change_signal"] == 1140.0
    assert result.loc[0, "etf_options_5d_volume_pressure_signal"] == 1880.0
    assert result.loc[0, "etf_options_5d_dealer_greeks_signal"] == -2.5
    assert result.loc[0, "etf_options_5d_composite_signal"] == np.mean([1140.0, 1880.0, -2.5])


def test_etf_options_bond_lookthrough_uses_latest_point_in_time_weight() -> None:
    bundle = _bond_lookthrough_bundle()

    result = ETF_options_positioning.compute(
        bundle,
        config=ETF_options_positioning.ETFOptionsAlphaConfig(signal_windows=("5D",), min_vol_observations=1),
    )

    assert result.loc[0, "etf_options_5d_lookthrough_asset_id"] == "LQD"
    assert result.loc[0, "etf_options_5d_lookthrough_weight"] == 0.25
    assert result.loc[0, "etf_options_5d_oi_change_bond_lookthrough_signal"] == 285.0


def test_etf_options_late_published_option_does_not_enter_component_signal() -> None:
    options = _options()
    options.loc[0, "publication_timestamp"] = pd.Timestamp("2026-01-03 12:00")
    bundle = _bundle(options)

    result = ETF_options_positioning.compute(
        bundle,
        config=ETF_options_positioning.ETFOptionsAlphaConfig(signal_windows=("5D",), min_vol_observations=1),
    )

    assert result.loc[0, "etf_options_5d_oi_change_signal"] == 140.0


def test_etf_options_alpha_missing_data_is_explicit() -> None:
    bundle = _bundle(None)

    result = ETF_options_positioning.compute(bundle)

    assert np.isnan(result.loc[0, "etf_options_positioning_28d_signal"])
    assert result.loc[0, "etf_options_positioning_28d_quality_flag"] == "missing_external_factors"


def test_etf_options_alpha_registered() -> None:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}

    assert index["ETF_OPT_POSITIONING"].module == "mechanical_alpha.alphas.ETF_options_positioning"
    assert index["ETF_OPT_POSITIONING"].status == "implemented"


def test_etf_options_checked_in_config_is_loadable() -> None:
    path = Path(__file__).parents[1] / "configs/alphas/etf_options_positioning.yaml"
    config = ETF_options_positioning.config_from_mapping(yaml.safe_load(path.read_text()))

    assert config.factor_id == "etf_option_position"
    assert config.signal_window == "28D"
    assert config.signal_windows == ("5D", "20D", "60D")
    assert config.variants == ("oi_change", "volume_pressure", "dealer_greeks", "composite")
    assert config.enable_bond_lookthrough is True
    assert config.min_abs_delta == 0.25
    assert config.max_abs_delta == 0.75


def _bundle(external_factors: pd.DataFrame | None) -> object:
    return bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["LQD"], "issuer_id": ["ETF"]}),
        events=pd.DataFrame(
            {
                "event_id": ["e1"],
                "prediction_timestamp": [pd.Timestamp("2026-01-03 10:00")],
                "bond_id": ["LQD"],
                "issuer_id": ["ETF"],
                "side": [1],
                "price": [100.0],
                "notional": [1_000_000.0],
            }
        ),
        metadata=SourceMetadata(
            name="fixture",
            side_convention=SideConvention.CUSTOMER,
            side_semantics="customer buy = +1",
            price_units="price points",
            size_units="par",
            point_in_time_safety="fixture",
        ),
        external_factors=external_factors,
    )


def _options() -> pd.DataFrame:
    dates = pd.to_datetime(
        [
            "2026-01-01 10:00",
            "2026-01-02 10:00",
            "2026-01-03 09:00",
            "2026-01-02 12:00",
            "2026-01-02 13:00",
            "2026-01-02 14:00",
        ]
    )
    return pd.DataFrame(
        {
            "timestamp": dates,
            "publication_timestamp": dates,
            "factor_id": ["etf_option_position"] * len(dates),
            "value": [0.0] * len(dates),
            "asset_id": ["LQD"] * len(dates),
            "option_type": ["call", "put", "call", "call", "put", "call"],
            "option_delta": [0.50, -0.45, 0.50, 0.50, -0.10, 0.90],
            "option_ttm_days": [30.0, 45.0, 60.0, 10.0, 30.0, 30.0],
            "expiry_date": [
                pd.Timestamp("2026-02-01"),
                pd.Timestamp("2026-02-15"),
                pd.Timestamp("2026-03-01"),
                pd.Timestamp("2026-01-03"),
                pd.Timestamp("2026-02-01"),
                pd.Timestamp("2026-02-01"),
            ],
            "option_notional": [100.0, 40.0, 70.0, 30.0, 20.0, 10.0],
            "open_interest": [12.0, 5.0, 3.0, 1.0, 1.0, 1.0],
            "previous_open_interest": [2.0, 5.0, 1.0, 1.0, 1.0, 1.0],
            "option_volume": [20.0, 10.0, 4.0, 1.0, 1.0, 1.0],
            "dealer_delta_exposure": [-10.0, 3.0, 2.0, 0.0, 0.0, 0.0],
            "dealer_gamma_exposure": [1.0, 1.0, 0.5, 0.0, 0.0, 0.0],
            "dealer_vega_exposure": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


def _bond_lookthrough_bundle() -> object:
    options = _options()
    weights = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01 09:00"), pd.Timestamp("2026-01-03 11:00")],
            "publication_timestamp": [pd.Timestamp("2026-01-01 09:00"), pd.Timestamp("2026-01-03 11:00")],
            "factor_id": ["etf_bond_lookthrough_weight", "etf_bond_lookthrough_weight"],
            "value": [0.25, 0.75],
            "asset_id": ["LQD", "LQD"],
            "bond_id": ["B1", "B1"],
            "weight_type": ["cr01", "cr01"],
        }
    )
    external = pd.concat([options, weights], ignore_index=True, sort=False)
    return bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["B1"], "issuer_id": ["ISS1"]}),
        events=pd.DataFrame(
            {
                "event_id": ["e1"],
                "prediction_timestamp": [pd.Timestamp("2026-01-03 10:00")],
                "bond_id": ["B1"],
                "issuer_id": ["ISS1"],
                "side": [1],
                "price": [100.0],
                "notional": [1_000_000.0],
            }
        ),
        metadata=SourceMetadata(
            name="fixture",
            side_convention=SideConvention.CUSTOMER,
            side_semantics="customer buy = +1",
            price_units="price points",
            size_units="par",
            point_in_time_safety="fixture",
        ),
        external_factors=external,
    )
