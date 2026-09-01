"""ETF options positioning signal.

This standalone alpha adapts the cookbook COFFEE/DTCC call-minus-put
positioning idea to fixed-income ETFs when point-in-time options positioning
data are supplied through `AlphaInputBundle.external_factors`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import FeatureDefinition, build_context
from mechanical_alpha.alpha_common.context import key
from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.fx_cookbook.coffee import ETFOptionsPositioningConfig, compute_coffee_imbalance


@dataclass(frozen=True)
class ETFOptionsAlphaConfig:
    """Portable config for ETF options positioning."""

    factor_id: str = "etf_option_position"
    signal_window: str = "28D"
    volatility_window_days: int = 252
    volatility_mode: str = "rolling_imbalance"
    min_abs_delta: float = 0.25
    max_abs_delta: float = 0.75
    min_ttm_days: float = 0.0
    max_ttm_days: float = 365.0
    min_vol_observations: int = 5

    def coffee_config(self) -> ETFOptionsPositioningConfig:
        return ETFOptionsPositioningConfig(
            factor_id=self.factor_id,
            signal_window=self.signal_window,
            volatility_window_days=self.volatility_window_days,
            volatility_mode=self.volatility_mode,
            min_abs_delta=self.min_abs_delta,
            max_abs_delta=self.max_abs_delta,
            min_ttm_days=self.min_ttm_days,
            max_ttm_days=self.max_ttm_days,
            min_vol_observations=self.min_vol_observations,
        )


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="ETF_OPT_POSITIONING",
        formula="sum(call_notional - put_notional over 4w) / train-declared trailing imbalance volatility",
        source_fields=(
            "external_factors.timestamp",
            "external_factors.publication_timestamp",
            "external_factors.asset_id",
            "external_factors.option_type",
            "external_factors.option_delta",
            "external_factors.option_ttm_days",
            "external_factors.option_notional",
        ),
        clock="calendar_time at bundle prediction timestamps",
        window="default 28D signal window, 252D volatility window",
        min_observations=5,
        missing_policy="NaN with quality flag when options positioning data or volatility scale is unavailable",
        expected_sign="positive means call-notional demand exceeds put-notional demand for the ETF",
        feature_class="directional",
        point_in_time_dependencies=(
            "uses external factor rows with publication_timestamp <= prediction_timestamp",
            "uses option rows strictly before the prediction timestamp",
            "does not read simulator truth or future returns",
        ),
        computational_cost="O(prediction_rows * option_rows_per_asset)",
    )


def compute(bundle: AlphaInputBundle, *, config: ETFOptionsAlphaConfig | None = None) -> pd.DataFrame:
    """Compute ETF options-positioning scores from public external factors."""

    cfg = config or ETFOptionsAlphaConfig()
    context = build_context(bundle)
    grid = context.prediction_grid.copy()
    if grid.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id"])
    options = bundle.external_factors
    if options is None or options.empty:
        return _empty_frame(grid, cfg, "missing_external_factors")
    rows: list[dict[str, object]] = []
    coffee_cfg = cfg.coffee_config()
    for prediction in grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        asset_id = str(prediction.bond_id)
        result = compute_coffee_imbalance(options, asof=asof, asset_id=asset_id, config=coffee_cfg)
        prefix = key("etf", "options", "positioning", cfg.signal_window)
        last_ts = result["last_observation_timestamp"]
        rows.append(
            {
                "prediction_timestamp": asof,
                "bond_id": asset_id,
                "issuer_id": prediction.issuer_id,
                f"{prefix}_signal": result["signal"],
                f"{prefix}_observed_imbalance": result["observed_imbalance"],
                f"{prefix}_volatility_scale": result["volatility_scale"],
                f"{prefix}_observation_count": result["observation_count"],
                f"{prefix}_last_observation_timestamp": last_ts,
                f"{prefix}_staleness_seconds": np.nan if pd.isna(last_ts) else float((asof - pd.Timestamp(last_ts)).total_seconds()),
                f"{prefix}_quality_flag": result["quality_flag"],
            }
        )
    return pd.DataFrame(rows).sort_values(["bond_id", "prediction_timestamp"]).reset_index(drop=True)


def config_from_mapping(payload: dict[str, object]) -> ETFOptionsAlphaConfig:
    """Build ETF options alpha config from YAML."""

    return ETFOptionsAlphaConfig(
        factor_id=str(payload.get("factor_id", "etf_option_position")),
        signal_window=str(payload.get("signal_window", "28D")),
        volatility_window_days=int(payload.get("volatility_window_days", 252)),
        volatility_mode=str(payload.get("volatility_mode", "rolling_imbalance")),
        min_abs_delta=float(payload.get("min_abs_delta", 0.25)),
        max_abs_delta=float(payload.get("max_abs_delta", 0.75)),
        min_ttm_days=float(payload.get("min_ttm_days", 0.0)),
        max_ttm_days=float(payload.get("max_ttm_days", 365.0)),
        min_vol_observations=int(payload.get("min_vol_observations", 5)),
    )


def _empty_frame(grid: pd.DataFrame, cfg: ETFOptionsAlphaConfig, reason: str) -> pd.DataFrame:
    frame = grid[["prediction_timestamp", "bond_id", "issuer_id"]].copy()
    prefix = key("etf", "options", "positioning", cfg.signal_window)
    frame[f"{prefix}_signal"] = np.nan
    frame[f"{prefix}_quality_flag"] = reason
    return frame
