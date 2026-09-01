import numpy as np
import pandas as pd

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


def test_etf_options_alpha_missing_data_is_explicit() -> None:
    bundle = _bundle(None)

    result = ETF_options_positioning.compute(bundle)

    assert np.isnan(result.loc[0, "etf_options_positioning_28d_signal"])
    assert result.loc[0, "etf_options_positioning_28d_quality_flag"] == "missing_external_factors"


def test_etf_options_alpha_registered() -> None:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}

    assert index["ETF_OPT_POSITIONING"].module == "mechanical_alpha.alphas.ETF_options_positioning"
    assert index["ETF_OPT_POSITIONING"].status == "implemented"


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
        }
    )
