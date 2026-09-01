"""COFFEE/DTCC positioning primitives and FI ETF adapter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


@dataclass(frozen=True)
class ETFOptionsPositioningConfig:
    """Configuration for the fixed-income ETF options-positioning adapter."""

    factor_id: str = "etf_option_position"
    signal_window: str = "28D"
    volatility_window_days: int = 252
    volatility_mode: str = "rolling_imbalance"
    min_abs_delta: float = 0.25
    max_abs_delta: float = 0.75
    min_ttm_days: float = 0.0
    max_ttm_days: float = 365.0
    min_vol_observations: int = 5
    epsilon: float = 1.0e-12


def normalize_option_direction(options: pd.DataFrame, *, config: ETFOptionsPositioningConfig | None = None) -> pd.DataFrame:
    """Normalize call/put notional so positive means upside demand in the ETF."""

    cfg = config or ETFOptionsPositioningConfig()
    frame = options.copy()
    if "factor_id" in frame.columns:
        frame = frame[frame["factor_id"].astype(str) == cfg.factor_id].copy()
    required = {"timestamp", "option_type", "option_delta", "option_ttm_days", "option_notional"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"ETF options positioning data missing columns: {missing}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    if "publication_timestamp" in frame.columns:
        frame["publication_timestamp"] = pd.to_datetime(frame["publication_timestamp"], utc=False)
    else:
        frame["publication_timestamp"] = frame["timestamp"]
    frame["asset_id"] = _asset_id(frame)
    frame["option_type"] = frame["option_type"].astype(str).str.lower()
    frame["option_delta"] = pd.to_numeric(frame["option_delta"], errors="coerce")
    frame["option_ttm_days"] = pd.to_numeric(frame["option_ttm_days"], errors="coerce")
    frame["option_notional"] = pd.to_numeric(frame["option_notional"], errors="coerce")
    sign = frame["option_type"].map({"call": 1.0, "c": 1.0, "put": -1.0, "p": -1.0})
    frame["directional_option_notional"] = sign * frame["option_notional"]
    return frame


def filter_coffee_options(options: pd.DataFrame, *, asof: pd.Timestamp | None = None, config: ETFOptionsPositioningConfig | None = None) -> pd.DataFrame:
    """Filter options using point-in-time availability, delta, and expiry rules."""

    cfg = config or ETFOptionsPositioningConfig()
    frame = normalize_option_direction(options, config=cfg)
    eligible = (
        frame["option_delta"].abs().between(cfg.min_abs_delta, cfg.max_abs_delta, inclusive="both")
        & frame["option_ttm_days"].gt(cfg.min_ttm_days)
        & frame["option_ttm_days"].lt(cfg.max_ttm_days)
        & frame["directional_option_notional"].notna()
    )
    if asof is not None:
        cutoff = pd.Timestamp(asof)
        eligible &= frame["publication_timestamp"] <= cutoff
        if "expiry_date" in frame.columns:
            expiry = pd.to_datetime(frame["expiry_date"], utc=False, errors="coerce")
            eligible &= expiry.dt.normalize() != cutoff.normalize()
    return frame[eligible].copy()


def compute_coffee_imbalance(
    options: pd.DataFrame,
    *,
    asof: pd.Timestamp,
    asset_id: str,
    config: ETFOptionsPositioningConfig | None = None,
) -> dict[str, float | str]:
    """Compute a four-week ETF call-minus-put notional imbalance and standardized signal."""

    cfg = config or ETFOptionsPositioningConfig()
    cutoff = pd.Timestamp(asof)
    frame = filter_coffee_options(options, asof=cutoff, config=cfg)
    frame = frame[frame["asset_id"].astype(str) == str(asset_id)].copy()
    if frame.empty:
        return _empty_signal("no_eligible_options")
    window_start = cutoff - pd.Timedelta(cfg.signal_window)
    recent = frame[(frame["timestamp"] > window_start) & (frame["timestamp"] < cutoff)].copy()
    observed = float(recent["directional_option_notional"].sum()) if not recent.empty else np.nan
    daily = _daily_imbalance(frame, cutoff, cfg)
    scale = _volatility_scale(daily, cfg)
    signal = np.nan if not np.isfinite(observed) or not np.isfinite(scale) else observed / (scale + cfg.epsilon)
    return {
        "observed_imbalance": observed,
        "volatility_scale": scale,
        "signal": float(signal) if np.isfinite(signal) else np.nan,
        "observation_count": float(len(recent)),
        "last_observation_timestamp": recent["timestamp"].max() if not recent.empty else pd.NaT,
        "quality_flag": "ok" if np.isfinite(signal) else "missing_or_zero_scale",
    }


def build_coffee_time_series_weights(signal: pd.Series, volatility: pd.Series) -> pd.Series:
    """Build inverse-volatility sign weights for ETF options positioning."""

    from mechanical_alpha.fx_cookbook.common import inverse_volatility_sign_weights

    return inverse_volatility_sign_weights(signal, volatility)


def build_coffee_cross_sectional_weights(signal: pd.Series) -> pd.Series:
    """Build equal-weight top/bottom rank-half weights for ETF options positioning."""

    from mechanical_alpha.fx_cookbook.common import equal_weight_rank_halves

    return equal_weight_rank_halves(signal)


def blocked_coffee_dtcc() -> BlockedStrategy:
    """Return a missing-data blocker for COFFEE/DTCC positioning."""

    return BlockedStrategy(
        strategy_id="COFFEE_DTCC_POSITIONING",
        status="BLOCKED_MISSING_DATA",
        reason="The current public bond bundle has no point-in-time DTCC/COFFEE options positioning fields.",
        blocking_decisions=("COFFEE-001", "COFFEE-002"),
        missing_inputs=("option_delta", "option_ttm", "call_put_notional"),
    )


def _asset_id(frame: pd.DataFrame) -> pd.Series:
    if "asset_id" in frame.columns:
        return frame["asset_id"].astype(str)
    if "bond_id" in frame.columns:
        return frame["bond_id"].astype(str)
    if "etf_ticker" in frame.columns:
        return frame["etf_ticker"].astype(str)
    raise ValueError("ETF options positioning data needs asset_id, bond_id, or etf_ticker")


def _daily_imbalance(frame: pd.DataFrame, cutoff: pd.Timestamp, cfg: ETFOptionsPositioningConfig) -> pd.Series:
    history_start = cutoff - pd.Timedelta(days=cfg.volatility_window_days)
    history = frame[(frame["timestamp"] >= history_start) & (frame["timestamp"] < cutoff)].copy()
    if history.empty:
        return pd.Series(dtype=float)
    daily_flow = history.groupby(history["timestamp"].dt.normalize())["directional_option_notional"].sum().sort_index()
    if cfg.volatility_mode == "daily_flow":
        return daily_flow
    if cfg.volatility_mode == "rolling_imbalance":
        return daily_flow.rolling(cfg.signal_window, min_periods=1).sum()
    raise ValueError("volatility_mode must be rolling_imbalance or daily_flow")


def _volatility_scale(daily: pd.Series, cfg: ETFOptionsPositioningConfig) -> float:
    clean = pd.to_numeric(daily, errors="coerce").dropna()
    if len(clean) < cfg.min_vol_observations:
        return np.nan
    scale = float(clean.std(ddof=1))
    return scale if np.isfinite(scale) and scale > 0 else np.nan


def _empty_signal(reason: str) -> dict[str, float | str]:
    return {
        "observed_imbalance": np.nan,
        "volatility_scale": np.nan,
        "signal": np.nan,
        "observation_count": 0.0,
        "last_observation_timestamp": pd.NaT,
        "quality_flag": reason,
    }
