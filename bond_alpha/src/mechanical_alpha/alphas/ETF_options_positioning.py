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
    signal_windows: tuple[str, ...] = ("5D", "20D", "60D")
    variants: tuple[str, ...] = ("oi_change", "volume_pressure", "dealer_greeks", "composite")
    lookthrough_factor_id: str = "etf_bond_lookthrough_weight"
    enable_bond_lookthrough: bool = True
    lookthrough_weight_type: str = "cr01"
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
        formula="separate ETF options OI-change, option-volume, dealer-greek, and composite pressures; optional ETF-to-bond lookthrough by frozen holdings/risk weights",
        source_fields=(
            "external_factors.timestamp",
            "external_factors.publication_timestamp",
            "external_factors.asset_id",
            "external_factors.option_type",
            "external_factors.option_delta",
            "external_factors.option_gamma",
            "external_factors.option_vega",
            "external_factors.option_ttm_days",
            "external_factors.option_notional",
            "external_factors.open_interest",
            "external_factors.previous_open_interest",
            "external_factors.option_volume",
            "external_factors.dealer_delta_exposure",
            "external_factors.dealer_gamma_exposure",
            "external_factors.dealer_vega_exposure",
            "external_factors.etf_bond_lookthrough_weight",
        ),
        clock="calendar_time at bundle prediction timestamps",
        window="default component windows: 5D, 20D, 60D; legacy 28D COFFEE-compatible signal retained",
        min_observations=5,
        missing_policy="NaN with quality flag when options, required mark columns, or lookthrough weights are unavailable",
        expected_sign="positive means ETF upside option pressure; bond lookthrough inherits the ETF signal times the configured ETF-bond weight",
        feature_class="directional",
        point_in_time_dependencies=(
            "uses external factor rows with publication_timestamp <= prediction_timestamp",
            "uses option rows strictly before the prediction timestamp",
            "uses lookthrough weights with publication_timestamp <= prediction_timestamp",
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
    option_frame = _option_rows(options, cfg)
    lookthrough = _lookthrough_rows(options, cfg)
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
        _add_component_features(
            rows[-1],
            option_frame,
            lookthrough,
            asof=asof,
            asset_id=asset_id,
            bond_id=str(prediction.bond_id),
            config=cfg,
        )
    return pd.DataFrame(rows).sort_values(["bond_id", "prediction_timestamp"]).reset_index(drop=True)


def config_from_mapping(payload: dict[str, object]) -> ETFOptionsAlphaConfig:
    """Build ETF options alpha config from YAML."""

    return ETFOptionsAlphaConfig(
        factor_id=str(payload.get("factor_id", "etf_option_position")),
        signal_window=str(payload.get("signal_window", "28D")),
        signal_windows=tuple(str(item) for item in payload.get("signal_windows", ("5D", "20D", "60D"))),
        variants=tuple(str(item) for item in payload.get("variants", ("oi_change", "volume_pressure", "dealer_greeks", "composite"))),
        lookthrough_factor_id=str(payload.get("lookthrough_factor_id", "etf_bond_lookthrough_weight")),
        enable_bond_lookthrough=bool(payload.get("enable_bond_lookthrough", True)),
        lookthrough_weight_type=str(payload.get("lookthrough_weight_type", "cr01")),
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


def _option_rows(external_factors: pd.DataFrame, cfg: ETFOptionsAlphaConfig) -> pd.DataFrame:
    frame = external_factors.copy()
    if "factor_id" in frame.columns:
        frame = frame[frame["factor_id"].astype(str) == cfg.factor_id].copy()
    if frame.empty:
        return frame
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    if "publication_timestamp" in frame.columns:
        frame["publication_timestamp"] = pd.to_datetime(frame["publication_timestamp"], utc=False)
    else:
        frame["publication_timestamp"] = frame["timestamp"]
    if "asset_id" not in frame.columns:
        if "etf_ticker" in frame.columns:
            frame["asset_id"] = frame["etf_ticker"].astype(str)
        elif "bond_id" in frame.columns:
            frame["asset_id"] = frame["bond_id"].astype(str)
    numeric = (
        "option_delta",
        "option_gamma",
        "option_vega",
        "option_ttm_days",
        "option_notional",
        "open_interest",
        "previous_open_interest",
        "oi_change",
        "option_volume",
        "dealer_delta_exposure",
        "dealer_gamma_exposure",
        "dealer_vega_exposure",
    )
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "option_type" in frame.columns:
        frame["option_type"] = frame["option_type"].astype(str).str.lower()
    return frame


def _lookthrough_rows(external_factors: pd.DataFrame, cfg: ETFOptionsAlphaConfig) -> pd.DataFrame:
    if "factor_id" not in external_factors.columns:
        return pd.DataFrame()
    frame = external_factors[external_factors["factor_id"].astype(str) == cfg.lookthrough_factor_id].copy()
    if frame.empty:
        return frame
    required = {"timestamp", "asset_id", "bond_id", "value"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    if "publication_timestamp" in frame.columns:
        frame["publication_timestamp"] = pd.to_datetime(frame["publication_timestamp"], utc=False)
    else:
        frame["publication_timestamp"] = frame["timestamp"]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["bond_id"] = frame["bond_id"].astype(str)
    frame["weight"] = pd.to_numeric(frame["value"], errors="coerce")
    if "weight_type" not in frame.columns:
        frame["weight_type"] = cfg.lookthrough_weight_type
    return frame


def _add_component_features(
    row: dict[str, object],
    options: pd.DataFrame,
    lookthrough: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    asset_id: str,
    bond_id: str,
    config: ETFOptionsAlphaConfig,
) -> None:
    etf_asset_id = _resolve_etf_asset_id(lookthrough, asof=asof, bond_id=bond_id, config=config) or asset_id
    for window in config.signal_windows:
        prefix = key("etf", "options", window)
        recent = _recent_options(options, asof=asof, asset_id=etf_asset_id, window=window, config=config)
        component_values: dict[str, float] = {}
        component_flags: dict[str, str] = {}
        for variant in config.variants:
            if variant == "composite":
                continue
            value, flag = _component_value(recent, variant)
            component_values[variant] = value
            component_flags[variant] = flag
            row[f"{prefix}_{variant}_signal"] = value
            row[f"{prefix}_{variant}_observation_count"] = float(len(recent)) if flag != "missing_required_columns" else 0.0
            row[f"{prefix}_{variant}_last_observation_timestamp"] = recent["timestamp"].max() if not recent.empty and "timestamp" in recent.columns else pd.NaT
            row[f"{prefix}_{variant}_quality_flag"] = flag
        if "composite" in config.variants:
            finite_components = [value for value in component_values.values() if np.isfinite(value)]
            composite = float(np.nanmean(finite_components)) if finite_components else np.nan
            row[f"{prefix}_composite_signal"] = composite
            row[f"{prefix}_composite_observation_count"] = float(len(finite_components))
            row[f"{prefix}_composite_quality_flag"] = "ok" if finite_components else "missing_components"
        if config.enable_bond_lookthrough:
            weight, weight_flag = _latest_lookthrough_weight(lookthrough, asof=asof, asset_id=etf_asset_id, bond_id=bond_id, config=config)
            row[f"{prefix}_lookthrough_asset_id"] = etf_asset_id
            row[f"{prefix}_lookthrough_weight"] = weight
            row[f"{prefix}_lookthrough_weight_quality_flag"] = weight_flag
            for variant, value in component_values.items():
                row[f"{prefix}_{variant}_bond_lookthrough_signal"] = np.nan if not np.isfinite(value) or not np.isfinite(weight) else value * weight
            if "composite" in config.variants:
                composite_value = row[f"{prefix}_composite_signal"]
                row[f"{prefix}_composite_bond_lookthrough_signal"] = (
                    np.nan if not np.isfinite(composite_value) or not np.isfinite(weight) else float(composite_value) * weight
                )


def _recent_options(options: pd.DataFrame, *, asof: pd.Timestamp, asset_id: str, window: str, config: ETFOptionsAlphaConfig) -> pd.DataFrame:
    if options.empty or "asset_id" not in options.columns:
        return pd.DataFrame()
    cutoff = pd.Timestamp(asof)
    window_start = cutoff - pd.Timedelta(window)
    frame = options[
        (options["asset_id"].astype(str) == str(asset_id))
        & (options["publication_timestamp"] <= cutoff)
        & (options["timestamp"] > window_start)
        & (options["timestamp"] < cutoff)
    ].copy()
    if frame.empty:
        return frame
    eligible = pd.Series(True, index=frame.index)
    if "option_delta" in frame.columns:
        eligible &= frame["option_delta"].abs().between(config.min_abs_delta, config.max_abs_delta, inclusive="both")
    if "option_ttm_days" in frame.columns:
        eligible &= frame["option_ttm_days"].gt(config.min_ttm_days) & frame["option_ttm_days"].lt(config.max_ttm_days)
    if "expiry_date" in frame.columns:
        expiry = pd.to_datetime(frame["expiry_date"], utc=False, errors="coerce")
        eligible &= expiry.dt.normalize() != cutoff.normalize()
    return frame[eligible].copy()


def _component_value(frame: pd.DataFrame, variant: str) -> tuple[float, str]:
    if frame.empty:
        return np.nan, "no_eligible_options"
    if variant == "oi_change":
        required = {"option_type", "open_interest", "option_notional"}
        if not required.issubset(frame.columns):
            return np.nan, "missing_required_columns"
        change = frame["oi_change"] if "oi_change" in frame.columns else frame["open_interest"] - frame.get("previous_open_interest", 0.0)
        weight = change * frame["option_notional"].fillna(1.0)
        return _signed_option_sum(frame, weight), "ok"
    if variant == "volume_pressure":
        required = {"option_type", "option_volume", "option_notional"}
        if not required.issubset(frame.columns):
            return np.nan, "missing_required_columns"
        weight = frame["option_volume"] * frame["option_notional"].fillna(1.0)
        return _signed_option_sum(frame, weight), "ok"
    if variant == "dealer_greeks":
        return _dealer_greek_pressure(frame)
    raise ValueError(f"unknown ETF options variant: {variant}")


def _signed_option_sum(frame: pd.DataFrame, weight: pd.Series) -> float:
    sign = frame["option_type"].astype(str).str.lower().map({"call": 1.0, "c": 1.0, "put": -1.0, "p": -1.0})
    value = sign * pd.to_numeric(weight, errors="coerce")
    total = float(value.sum(skipna=True))
    return total if np.isfinite(total) else np.nan


def _dealer_greek_pressure(frame: pd.DataFrame) -> tuple[float, str]:
    direct_columns = [column for column in ("dealer_delta_exposure", "dealer_gamma_exposure", "dealer_vega_exposure") if column in frame.columns]
    if direct_columns:
        total = float(frame[direct_columns].sum(axis=1, skipna=True).sum(skipna=True))
        return (total if np.isfinite(total) else np.nan), "ok"
    required = {"option_delta", "option_gamma", "option_notional", "open_interest"}
    if not required.issubset(frame.columns):
        return np.nan, "missing_required_columns"
    exposure = (
        frame["option_delta"].fillna(0.0) * frame["open_interest"].fillna(0.0) * frame["option_notional"].fillna(1.0)
        + frame["option_gamma"].fillna(0.0).abs() * frame["open_interest"].fillna(0.0) * frame["option_notional"].fillna(1.0)
    )
    total = float(exposure.sum(skipna=True))
    return (total if np.isfinite(total) else np.nan), "estimated_from_chain"


def _resolve_etf_asset_id(
    lookthrough: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    bond_id: str,
    config: ETFOptionsAlphaConfig,
) -> str | None:
    if lookthrough.empty:
        return None
    rows = lookthrough[
        (lookthrough["bond_id"].astype(str) == str(bond_id))
        & (lookthrough["publication_timestamp"] <= pd.Timestamp(asof))
        & (lookthrough["timestamp"] < pd.Timestamp(asof))
        & (lookthrough["weight_type"].astype(str) == config.lookthrough_weight_type)
    ].copy()
    if rows.empty:
        return None
    latest = rows.sort_values(["timestamp", "asset_id"], kind="mergesort").iloc[-1]
    return str(latest["asset_id"])


def _latest_lookthrough_weight(
    lookthrough: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    asset_id: str,
    bond_id: str,
    config: ETFOptionsAlphaConfig,
) -> tuple[float, str]:
    if lookthrough.empty:
        return np.nan, "missing_lookthrough_weights"
    rows = lookthrough[
        (lookthrough["asset_id"].astype(str) == str(asset_id))
        & (lookthrough["bond_id"].astype(str) == str(bond_id))
        & (lookthrough["publication_timestamp"] <= pd.Timestamp(asof))
        & (lookthrough["timestamp"] < pd.Timestamp(asof))
        & (lookthrough["weight_type"].astype(str) == config.lookthrough_weight_type)
    ].copy()
    if rows.empty:
        return np.nan, "no_point_in_time_weight"
    weight = float(rows.sort_values("timestamp", kind="mergesort").iloc[-1]["weight"])
    return (weight if np.isfinite(weight) else np.nan), "ok" if np.isfinite(weight) else "invalid_weight"
