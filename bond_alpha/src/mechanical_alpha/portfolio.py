"""Portable target-position construction from alpha signal frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd

WeightMethod = Literal["rank_long_short", "signal_proportional"]
RiskUnit = Literal["notional", "dv01", "cr01"]


@dataclass(frozen=True)
class PortfolioConfig:
    """Configuration for deterministic single-period portfolio targets."""

    signal_col: str = "signal"
    instrument_col: str = "bond_id"
    group_cols: tuple[str, ...] | None = None
    weight_method: WeightMethod = "rank_long_short"
    risk_unit: RiskUnit = "notional"
    risk_col: str | None = None
    gross_target: float = 1.0
    max_abs_position: float | None = None
    cap_col: str | None = None


def construct_target_positions(signals: pd.DataFrame, config: PortfolioConfig | None = None) -> pd.DataFrame:
    """Convert alpha signals into target positions.

    The output preserves the input row order. `target_exposure` is the signed
    risk-unit exposure. `target_position` is exposure divided by the selected
    per-position risk unit.
    """

    cfg = config or PortfolioConfig()
    _validate_inputs(signals, cfg)
    output = signals.copy()
    output["_portfolio_order"] = np.arange(len(output), dtype=int)
    output["target_weight"] = 0.0
    output["risk_unit_value"] = np.nan
    output["target_exposure"] = 0.0
    output["target_position"] = 0.0
    output["realized_gross_exposure"] = 0.0
    output["portfolio_quality_flag"] = "flat_no_valid_signals"

    if signals.empty:
        return output.drop(columns=["_portfolio_order"])

    group_cols = _resolve_group_cols(output, cfg)
    if group_cols:
        grouped = output.groupby(list(group_cols), sort=False, dropna=False, group_keys=False)
        pieces = [_construct_group(group.copy(), cfg) for _, group in grouped]
        result = pd.concat(pieces, axis=0) if pieces else output
    else:
        result = _construct_group(output, cfg)

    return result.sort_values("_portfolio_order", kind="mergesort").drop(columns=["_portfolio_order"])


def portfolio_from_signals(
    signals: pd.DataFrame,
    *,
    signal_col: str = "signal",
    instrument_col: str = "bond_id",
    group_cols: Iterable[str] | None = None,
    weight_method: WeightMethod = "rank_long_short",
    risk_unit: RiskUnit = "notional",
    risk_col: str | None = None,
    gross_target: float = 1.0,
    max_abs_position: float | None = None,
    cap_col: str | None = None,
) -> pd.DataFrame:
    """Convenience wrapper for callers that prefer keyword arguments."""

    return construct_target_positions(
        signals,
        PortfolioConfig(
            signal_col=signal_col,
            instrument_col=instrument_col,
            group_cols=None if group_cols is None else tuple(group_cols),
            weight_method=weight_method,
            risk_unit=risk_unit,
            risk_col=risk_col,
            gross_target=gross_target,
            max_abs_position=max_abs_position,
            cap_col=cap_col,
        ),
    )


def _construct_group(group: pd.DataFrame, cfg: PortfolioConfig) -> pd.DataFrame:
    signal = pd.to_numeric(group[cfg.signal_col], errors="coerce")
    raw = _raw_weights(group, signal, cfg)
    exposures = _normalize_gross(raw, cfg.gross_target)
    risk_values, invalid_risk = _risk_values(group, cfg)
    positions = _safe_divide(exposures, risk_values)
    positions = _apply_caps(group, positions, cfg)
    exposures = positions * risk_values.fillna(0.0)
    gross = float(np.nansum(np.abs(exposures.to_numpy(dtype=float))))

    group["target_weight"] = _safe_divide(exposures, gross) if gross > 0 else 0.0
    group["risk_unit_value"] = risk_values
    group["target_exposure"] = exposures
    group["target_position"] = positions
    group["realized_gross_exposure"] = gross
    group["portfolio_quality_flag"] = _quality_flag(signal, positions, invalid_risk, gross)
    return group


def _raw_weights(group: pd.DataFrame, signal: pd.Series, cfg: PortfolioConfig) -> pd.Series:
    if cfg.weight_method == "signal_proportional":
        return signal.replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    if cfg.weight_method == "rank_long_short":
        return _rank_long_short(group, signal, cfg.instrument_col)
    raise ValueError(f"unknown weight_method: {cfg.weight_method}")


def _rank_long_short(group: pd.DataFrame, signal: pd.Series, instrument_col: str) -> pd.Series:
    raw = pd.Series(0.0, index=group.index, dtype=float)
    valid = signal.replace([np.inf, -np.inf], np.nan).dropna()
    if len(valid) < 2:
        return raw

    ordered = group.loc[valid.index, [instrument_col]].copy()
    ordered["_signal"] = valid
    ordered["_original_position"] = np.arange(len(ordered), dtype=int)
    ordered = ordered.sort_values(["_signal", instrument_col, "_original_position"], kind="mergesort")

    names_per_side = len(ordered) // 2
    if names_per_side <= 0:
        return raw
    raw.loc[ordered.index[:names_per_side]] = -1.0 / float(names_per_side)
    raw.loc[ordered.index[-names_per_side:]] = 1.0 / float(names_per_side)
    return raw


def _normalize_gross(values: pd.Series, gross_target: float) -> pd.Series:
    if gross_target < 0 or not np.isfinite(gross_target):
        raise ValueError("gross_target must be finite and nonnegative")
    denominator = float(values.abs().sum())
    if denominator <= 0 or gross_target == 0:
        return pd.Series(0.0, index=values.index, dtype=float)
    return values.astype(float) * (float(gross_target) / denominator)


def _risk_values(group: pd.DataFrame, cfg: PortfolioConfig) -> tuple[pd.Series, pd.Series]:
    risk_col = cfg.risk_col or cfg.risk_unit
    if risk_col in group.columns:
        values = pd.to_numeric(group[risk_col], errors="coerce").abs().astype(float)
    elif cfg.risk_unit == "notional":
        values = pd.Series(1.0, index=group.index, dtype=float)
    else:
        raise ValueError(f"risk_col '{risk_col}' is required for {cfg.risk_unit} scaling")
    invalid = (~np.isfinite(values)) | (values <= 0.0)
    return values.where(~invalid, np.nan), invalid


def _apply_caps(group: pd.DataFrame, positions: pd.Series, cfg: PortfolioConfig) -> pd.Series:
    caps: pd.Series | None = None
    if cfg.max_abs_position is not None:
        if cfg.max_abs_position < 0 or not np.isfinite(cfg.max_abs_position):
            raise ValueError("max_abs_position must be finite and nonnegative")
        caps = pd.Series(float(cfg.max_abs_position), index=group.index, dtype=float)
    if cfg.cap_col is not None:
        if cfg.cap_col not in group.columns:
            raise ValueError(f"missing cap column: {cfg.cap_col}")
        cap_values = pd.to_numeric(group[cfg.cap_col], errors="coerce").abs().astype(float)
        caps = cap_values if caps is None else np.minimum(caps, cap_values)
    if caps is None:
        return positions.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    valid_caps = caps.where(np.isfinite(caps) & (caps >= 0.0), 0.0)
    return positions.clip(lower=-valid_caps, upper=valid_caps).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _safe_divide(numerator: pd.Series, denominator: pd.Series | float) -> pd.Series:
    if np.isscalar(denominator):
        denom = float(denominator)
        if denom <= 0 or not np.isfinite(denom):
            return pd.Series(0.0, index=numerator.index, dtype=float)
        return numerator.astype(float) / denom
    denom_series = denominator.astype(float).replace(0.0, np.nan)
    result = numerator.astype(float) / denom_series
    return result.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def _quality_flag(signal: pd.Series, positions: pd.Series, invalid_risk: pd.Series, gross: float) -> str:
    if signal.replace([np.inf, -np.inf], np.nan).dropna().empty:
        return "flat_no_valid_signals"
    if gross <= 0:
        return "flat_after_scaling"
    if bool(invalid_risk.any()):
        return "partial_invalid_risk_unit"
    if bool((positions == 0.0).all()):
        return "flat_after_caps"
    return "ok"


def _resolve_group_cols(frame: pd.DataFrame, cfg: PortfolioConfig) -> tuple[str, ...]:
    if cfg.group_cols is not None:
        missing = [column for column in cfg.group_cols if column not in frame.columns]
        if missing:
            raise ValueError(f"missing group columns: {missing}")
        return tuple(cfg.group_cols)
    for candidate in ("prediction_timestamp", "timestamp", "date"):
        if candidate in frame.columns:
            return (candidate,)
    return ()


def _validate_inputs(signals: pd.DataFrame, cfg: PortfolioConfig) -> None:
    missing = [column for column in (cfg.signal_col, cfg.instrument_col) if column not in signals.columns]
    if missing:
        raise ValueError(f"signals missing required columns: {missing}")
    valid_methods: set[str] = {"rank_long_short", "signal_proportional"}
    if cfg.weight_method not in valid_methods:
        raise ValueError(f"weight_method must be one of {sorted(valid_methods)}")
    valid_risk_units: set[str] = {"notional", "dv01", "cr01"}
    if cfg.risk_unit not in valid_risk_units:
        raise ValueError(f"risk_unit must be one of {sorted(valid_risk_units)}")
    if cfg.group_cols is not None and not isinstance(cfg.group_cols, tuple):
        raise TypeError("group_cols must be a tuple of column names or None")


__all__ = ["PortfolioConfig", "construct_target_positions", "portfolio_from_signals"]
