"""Carry cookbook operators and bond par-adjusted curve adapter."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mechanical_alpha.fx_cookbook.common import BlockedStrategy


def compute_fx_carry(spot: pd.DataFrame, forward: pd.DataFrame, *, quote_orientation: str) -> pd.DataFrame:
    """Compute FX carry from spot and forward panels with explicit orientation."""

    if quote_orientation == "base_per_quote":
        return forward / spot.replace(0.0, np.nan) - 1.0
    if quote_orientation == "quote_per_base":
        return spot / forward.replace(0.0, np.nan) - 1.0
    raise ValueError("quote_orientation must be base_per_quote or quote_per_base")


def smooth_carry(carry: pd.DataFrame, *, window: int) -> pd.DataFrame:
    """Smooth carry with a trailing mean."""

    if window <= 0:
        raise ValueError("window must be positive")
    return carry.rolling(window=window, min_periods=1).mean()


@dataclass(frozen=True)
class ParAdjustedCurveConfig:
    """Unit-aware configuration for Martin-style bond carry calculations."""

    horizon_years: float = 1.0 / 252.0
    spread_unit: str = "bps"
    coupon_unit: str = "percent"
    rpv01_unit: str = "price_per_decimal"
    output_unit: str = "price_points"


@dataclass(frozen=True)
class ParAdjustedCarryInputs:
    """Inputs to equations 18-21 from the par-adjusted spread framework."""

    par_adjusted_spread: float
    model_par_spread: float
    rolled_model_par_spread: float
    risky_pv01: float
    rolled_risky_pv01: float
    coupon_minus_riskfree: float


def compute_par_adjusted_carry_rolldown(
    inputs: ParAdjustedCarryInputs,
    config: ParAdjustedCurveConfig | None = None,
) -> dict[str, float]:
    """Compute bond credit carry, roll-down, RV, and total return.

    The equations follow Martin's par-adjusted spread decomposition:

    carry = c' dt + (s_bar - c') (Pi(T) - Pi(T - dt))
    rolldown = (s_hat(T) - s_hat(T - dt)) Pi(T - dt)
    rv = (s_bar - s_hat(T)) Pi(T - dt)

    Positive values are return-oriented price contributions.
    """

    cfg = config or ParAdjustedCurveConfig()
    if cfg.horizon_years <= 0:
        raise ValueError("horizon_years must be positive")

    s_bar = _rate_to_decimal(inputs.par_adjusted_spread, cfg.spread_unit)
    s_hat = _rate_to_decimal(inputs.model_par_spread, cfg.spread_unit)
    s_hat_rolled = _rate_to_decimal(inputs.rolled_model_par_spread, cfg.spread_unit)
    c_prime = _rate_to_decimal(inputs.coupon_minus_riskfree, cfg.coupon_unit)
    pi_t = _rpv01_to_price_per_decimal(inputs.risky_pv01, cfg.rpv01_unit)
    pi_rolled = _rpv01_to_price_per_decimal(inputs.rolled_risky_pv01, cfg.rpv01_unit)

    carry = c_prime * cfg.horizon_years + (s_bar - c_prime) * (pi_t - pi_rolled)
    rolldown = (s_hat - s_hat_rolled) * pi_rolled
    relative_value = (s_bar - s_hat) * pi_rolled
    total = carry + rolldown + relative_value
    scale = 100.0 if cfg.output_unit == "price_points" else 1.0
    if cfg.output_unit not in {"price_points", "price_fraction"}:
        raise ValueError("output_unit must be price_points or price_fraction")
    return {
        "carry": float(carry * scale),
        "rolldown": float(rolldown * scale),
        "relative_value": float(relative_value * scale),
        "total_return": float(total * scale),
    }


def interpolate_curve_value(
    curve: pd.DataFrame,
    *,
    value_column: str,
    maturity_years: float,
    tenor_column: str = "tenor_years",
) -> float:
    """Linearly interpolate one fitted curve column by tenor."""

    if value_column not in curve.columns:
        raise ValueError(f"curve missing required column: {value_column}")
    if tenor_column not in curve.columns:
        raise ValueError(f"curve missing required column: {tenor_column}")
    clean = curve[[tenor_column, value_column]].dropna().sort_values(tenor_column)
    if clean.empty:
        return np.nan
    tenors = clean[tenor_column].to_numpy(dtype=float)
    values = clean[value_column].to_numpy(dtype=float)
    if len(clean) == 1:
        return float(values[0])
    clipped = float(np.clip(maturity_years, tenors.min(), tenors.max()))
    return float(np.interp(clipped, tenors, values))


def _rate_to_decimal(value: float, unit: str) -> float:
    if pd.isna(value):
        return np.nan
    if unit == "decimal":
        return float(value)
    if unit == "bps":
        return float(value) / 10_000.0
    if unit == "percent":
        return float(value) / 100.0
    raise ValueError("rate unit must be decimal, bps, or percent")


def _rpv01_to_price_per_decimal(value: float, unit: str) -> float:
    if pd.isna(value):
        return np.nan
    if unit == "price_per_decimal":
        return float(value)
    if unit == "price_per_bp":
        return float(value) * 10_000.0
    if unit == "fraction_per_decimal":
        return float(value)
    raise ValueError("rpv01_unit must be price_per_decimal, price_per_bp, or fraction_per_decimal")


def blocked_carry() -> BlockedStrategy:
    """Return the source-literal carry blocker."""

    return BlockedStrategy(
        strategy_id="FX_CARRY_LITERAL",
        status="BLOCKED_HUMAN",
        reason="Carry needs explicit quote orientation, financing convention, and bond carry/roll-down translation.",
        blocking_decisions=("CARRY-001", "CARRY-002", "CARRY-003"),
        missing_inputs=("fx_forward", "financing_curve"),
    )
