"""Bond carry, roll-down, and relative-value alpha from a par-adjusted spread curve."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mechanical_alpha.alpha_common import FeatureDefinition, build_context
from mechanical_alpha.alpha_common.context import key
from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.fx_cookbook.carry import (
    ParAdjustedCarryInputs,
    ParAdjustedCurveConfig,
    compute_par_adjusted_carry_rolldown,
    interpolate_curve_value,
)


@dataclass(frozen=True)
class BondCarryRolldownConfig:
    """Portable config for a PIT par-adjusted spread curve table."""

    factor_id: str = "par_adjusted_spread_curve"
    horizons: tuple[str, ...] = ("1d", "5d")
    spread_unit: str = "bps"
    coupon_unit: str = "percent"
    rpv01_unit: str = "price_per_decimal"
    output_unit: str = "price_points"
    timestamp_column: str = "timestamp"
    publication_timestamp_column: str = "publication_timestamp"
    bond_id_column: str = "bond_id"
    issuer_id_column: str = "issuer_id"
    curve_id_column: str = "curve_id"
    tenor_column: str = "tenor_years"
    maturity_column: str = "years_to_maturity"
    par_adjusted_spread_column: str = "par_adjusted_spread"
    model_par_spread_column: str = "model_par_spread"
    risky_pv01_column: str = "risky_pv01"
    coupon_minus_riskfree_column: str = "coupon_minus_riskfree"
    min_curve_points: int = 2


def describe() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="BOND_CARRY_ROLLDOWN",
        formula="Martin par-adjusted spread curve decomposition: carry, rolldown, RV, and total return by horizon",
        source_fields=(
            "external_factors.timestamp",
            "external_factors.factor_id",
            "external_factors.bond_id",
            "external_factors.curve_id or issuer_id",
            "external_factors.tenor_years",
            "external_factors.par_adjusted_spread",
            "external_factors.model_par_spread",
            "external_factors.risky_pv01",
            "external_factors.coupon_minus_riskfree",
        ),
        clock="calendar_time at bundle prediction timestamps",
        window="latest curve snapshot published before prediction timestamp",
        min_observations=2,
        missing_policy="NaN plus quality flag when PIT curve, maturity, spread, or RPV01 inputs are unavailable",
        expected_sign="positive means higher expected bond price return from carry, rolldown, and cheapness to the curve",
        feature_class="relative_value",
        point_in_time_dependencies=(
            "uses curve rows with timestamp < prediction timestamp",
            "uses publication_timestamp <= prediction_timestamp when available",
            "does not use future prices, future fair values, labels, or simulator truth",
        ),
        computational_cost="O(prediction_rows * curve_rows_for_issuer)",
        version="0.1.0",
    )


def compute(bundle: AlphaInputBundle, *, config: BondCarryRolldownConfig | None = None) -> pd.DataFrame:
    """Compute carry, roll-down, RV, and total-return signals from public curve rows."""

    cfg = config or BondCarryRolldownConfig()
    context = build_context(bundle)
    grid = context.prediction_grid.copy()
    if grid.empty:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id"])
    curves = _curve_rows(bundle.external_factors, cfg)
    if curves.empty:
        return _empty_frame(grid, cfg, "missing_par_adjusted_curve")

    rows: list[dict[str, object]] = []
    for prediction in grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        bond_id = str(prediction.bond_id)
        issuer_id = "" if pd.isna(prediction.issuer_id) else str(prediction.issuer_id)
        row: dict[str, object] = {"prediction_timestamp": asof, "bond_id": bond_id, "issuer_id": prediction.issuer_id}
        snapshot = _latest_snapshot(curves, cfg, bond_id=bond_id, issuer_id=issuer_id, asof=asof)
        if snapshot.empty:
            _add_missing_outputs(row, cfg, "no_pit_curve_snapshot")
            rows.append(row)
            continue
        bond_row = _bond_curve_row(snapshot, cfg, bond_id)
        curve_points = _curve_points(snapshot, cfg, bond_row)
        if bond_row is None or len(curve_points) < cfg.min_curve_points:
            _add_missing_outputs(row, cfg, "insufficient_curve_points")
            rows.append(row)
            continue
        _add_curve_outputs(row, bond_row, curve_points, cfg)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["bond_id", "prediction_timestamp"]).reset_index(drop=True)


def config_from_mapping(payload: dict[str, object]) -> BondCarryRolldownConfig:
    """Build alpha config from YAML."""

    return BondCarryRolldownConfig(
        factor_id=str(payload.get("factor_id", "par_adjusted_spread_curve")),
        horizons=tuple(str(item) for item in payload.get("horizons", ("1d", "5d"))),
        spread_unit=str(payload.get("spread_unit", "bps")),
        coupon_unit=str(payload.get("coupon_unit", "percent")),
        rpv01_unit=str(payload.get("rpv01_unit", "price_per_decimal")),
        output_unit=str(payload.get("output_unit", "price_points")),
        timestamp_column=str(payload.get("timestamp_column", "timestamp")),
        publication_timestamp_column=str(payload.get("publication_timestamp_column", "publication_timestamp")),
        bond_id_column=str(payload.get("bond_id_column", "bond_id")),
        issuer_id_column=str(payload.get("issuer_id_column", "issuer_id")),
        curve_id_column=str(payload.get("curve_id_column", "curve_id")),
        tenor_column=str(payload.get("tenor_column", "tenor_years")),
        maturity_column=str(payload.get("maturity_column", "years_to_maturity")),
        par_adjusted_spread_column=str(payload.get("par_adjusted_spread_column", "par_adjusted_spread")),
        model_par_spread_column=str(payload.get("model_par_spread_column", "model_par_spread")),
        risky_pv01_column=str(payload.get("risky_pv01_column", "risky_pv01")),
        coupon_minus_riskfree_column=str(payload.get("coupon_minus_riskfree_column", "coupon_minus_riskfree")),
        min_curve_points=int(payload.get("min_curve_points", 2)),
    )


def _curve_rows(external_factors: pd.DataFrame | None, cfg: BondCarryRolldownConfig) -> pd.DataFrame:
    if external_factors is None or external_factors.empty:
        return pd.DataFrame()
    frame = external_factors.copy()
    if "factor_id" not in frame.columns:
        return pd.DataFrame()
    frame = frame[frame["factor_id"].astype(str) == cfg.factor_id].copy()
    if frame.empty:
        return frame
    required = (
        cfg.timestamp_column,
        cfg.tenor_column,
        cfg.par_adjusted_spread_column,
        cfg.model_par_spread_column,
        cfg.risky_pv01_column,
        cfg.coupon_minus_riskfree_column,
    )
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"par-adjusted curve rows missing required columns: {missing}")
    frame[cfg.timestamp_column] = pd.to_datetime(frame[cfg.timestamp_column], utc=False)
    if cfg.publication_timestamp_column in frame.columns:
        frame[cfg.publication_timestamp_column] = pd.to_datetime(frame[cfg.publication_timestamp_column], utc=False)
    for column in (
        cfg.tenor_column,
        cfg.maturity_column,
        cfg.par_adjusted_spread_column,
        cfg.model_par_spread_column,
        cfg.risky_pv01_column,
        cfg.coupon_minus_riskfree_column,
    ):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _latest_snapshot(
    curves: pd.DataFrame,
    cfg: BondCarryRolldownConfig,
    *,
    bond_id: str,
    issuer_id: str,
    asof: pd.Timestamp,
) -> pd.DataFrame:
    cutoff = _align_timestamp_for_series(asof, curves[cfg.timestamp_column])
    prior = curves[curves[cfg.timestamp_column] < cutoff].copy()
    if cfg.publication_timestamp_column in prior.columns:
        publication_cutoff = _align_timestamp_for_series(asof, prior[cfg.publication_timestamp_column])
        prior = prior[prior[cfg.publication_timestamp_column] <= publication_cutoff].copy()
    if cfg.bond_id_column in prior.columns:
        matching_bond = prior[prior[cfg.bond_id_column].astype(str) == bond_id].copy()
        if not matching_bond.empty:
            prior = matching_bond
    if cfg.issuer_id_column in prior.columns and issuer_id:
        matching_issuer = prior[prior[cfg.issuer_id_column].astype(str) == issuer_id].copy()
        if not matching_issuer.empty:
            prior = matching_issuer
    if prior.empty:
        return prior
    latest_ts = prior[cfg.timestamp_column].max()
    return prior[prior[cfg.timestamp_column] == latest_ts].copy()


def _bond_curve_row(snapshot: pd.DataFrame, cfg: BondCarryRolldownConfig, bond_id: str) -> pd.Series | None:
    if cfg.bond_id_column in snapshot.columns:
        bond_rows = snapshot[snapshot[cfg.bond_id_column].astype(str) == bond_id]
        if not bond_rows.empty:
            exact = bond_rows[bond_rows[cfg.maturity_column].notna()] if cfg.maturity_column in bond_rows.columns else bond_rows
            return exact.iloc[0]
    if cfg.maturity_column not in snapshot.columns:
        return None
    rows = snapshot[snapshot[cfg.maturity_column].notna()]
    if rows.empty:
        return None
    return rows.iloc[0]


def _curve_points(snapshot: pd.DataFrame, cfg: BondCarryRolldownConfig, bond_row: pd.Series) -> pd.DataFrame:
    curve = snapshot.copy()
    if cfg.curve_id_column in snapshot.columns and cfg.curve_id_column in bond_row and pd.notna(bond_row[cfg.curve_id_column]):
        curve = curve[curve[cfg.curve_id_column].astype(str) == str(bond_row[cfg.curve_id_column])].copy()
    if curve.empty:
        curve = snapshot.copy()
    return curve.dropna(subset=[cfg.tenor_column, cfg.model_par_spread_column, cfg.risky_pv01_column])


def _add_curve_outputs(
    row: dict[str, object],
    bond_row: pd.Series,
    curve_points: pd.DataFrame,
    cfg: BondCarryRolldownConfig,
) -> None:
    maturity = _get_float(bond_row, cfg.maturity_column)
    if not np.isfinite(maturity) or maturity <= 0:
        _add_missing_outputs(row, cfg, "missing_or_invalid_maturity")
        return
    last_ts = pd.Timestamp(bond_row[cfg.timestamp_column])
    for horizon in cfg.horizons:
        years = _horizon_to_years(horizon)
        rolled_maturity = max(maturity - years, 1.0 / 365.0)
        inputs = ParAdjustedCarryInputs(
            par_adjusted_spread=_get_float(bond_row, cfg.par_adjusted_spread_column),
            model_par_spread=interpolate_curve_value(
                curve_points,
                value_column=cfg.model_par_spread_column,
                maturity_years=maturity,
                tenor_column=cfg.tenor_column,
            ),
            rolled_model_par_spread=interpolate_curve_value(
                curve_points,
                value_column=cfg.model_par_spread_column,
                maturity_years=rolled_maturity,
                tenor_column=cfg.tenor_column,
            ),
            risky_pv01=interpolate_curve_value(
                curve_points,
                value_column=cfg.risky_pv01_column,
                maturity_years=maturity,
                tenor_column=cfg.tenor_column,
            ),
            rolled_risky_pv01=interpolate_curve_value(
                curve_points,
                value_column=cfg.risky_pv01_column,
                maturity_years=rolled_maturity,
                tenor_column=cfg.tenor_column,
            ),
            coupon_minus_riskfree=_get_float(bond_row, cfg.coupon_minus_riskfree_column),
        )
        values = compute_par_adjusted_carry_rolldown(
            inputs,
            ParAdjustedCurveConfig(
                horizon_years=years,
                spread_unit=cfg.spread_unit,
                coupon_unit=cfg.coupon_unit,
                rpv01_unit=cfg.rpv01_unit,
                output_unit=cfg.output_unit,
            ),
        )
        prefix = key("bond", "carry", "rolldown", horizon)
        for name, value in values.items():
            row[f"{prefix}_{name}"] = value
        row[f"{prefix}_model_par_spread"] = inputs.model_par_spread
        row[f"{prefix}_rolled_model_par_spread"] = inputs.rolled_model_par_spread
        row[f"{prefix}_risky_pv01"] = inputs.risky_pv01
        row[f"{prefix}_rolled_risky_pv01"] = inputs.rolled_risky_pv01
        row[f"{prefix}_observation_count"] = int(len(curve_points))
        row[f"{prefix}_last_observation_timestamp"] = last_ts
        row[f"{prefix}_staleness_seconds"] = _seconds_between(pd.Timestamp(row["prediction_timestamp"]), last_ts)
        row[f"{prefix}_quality_flag"] = "ok"


def _add_missing_outputs(row: dict[str, object], cfg: BondCarryRolldownConfig, reason: str) -> None:
    for horizon in cfg.horizons:
        prefix = key("bond", "carry", "rolldown", horizon)
        for name in ("carry", "rolldown", "relative_value", "total_return"):
            row[f"{prefix}_{name}"] = np.nan
        row[f"{prefix}_observation_count"] = 0
        row[f"{prefix}_last_observation_timestamp"] = pd.NaT
        row[f"{prefix}_staleness_seconds"] = np.nan
        row[f"{prefix}_quality_flag"] = reason


def _empty_frame(grid: pd.DataFrame, cfg: BondCarryRolldownConfig, reason: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for prediction in grid.itertuples(index=False):
        row: dict[str, object] = {
            "prediction_timestamp": prediction.prediction_timestamp,
            "bond_id": prediction.bond_id,
            "issuer_id": prediction.issuer_id,
        }
        _add_missing_outputs(row, cfg, reason)
        rows.append(row)
    return pd.DataFrame(rows)


def _horizon_to_years(horizon: str) -> float:
    text = str(horizon).strip().lower()
    if text.endswith("bday"):
        value = float(text[: -len("bday")])
        return value / 252.0
    if text.endswith("bd"):
        value = float(text[: -len("bd")])
        return value / 252.0
    if text.endswith("d"):
        return float(text[:-1]) / 252.0
    if text.endswith("h"):
        return float(text[:-1]) / (252.0 * 6.5)
    raise ValueError(f"unsupported horizon: {horizon}")


def _get_float(row: pd.Series, column: str) -> float:
    if column not in row or pd.isna(row[column]):
        return np.nan
    return float(row[column])


def _align_timestamp_for_series(timestamp: pd.Timestamp, series: pd.Series) -> pd.Timestamp:
    ts = pd.Timestamp(timestamp)
    dtype = series.dtype
    tz = getattr(dtype, "tz", None)
    if tz is None and ts.tzinfo is not None:
        return ts.tz_convert(None)
    if tz is not None and ts.tzinfo is None:
        return ts.tz_localize(tz)
    return ts


def _seconds_between(left: pd.Timestamp, right: pd.Timestamp) -> float:
    lhs = pd.Timestamp(left)
    rhs = pd.Timestamp(right)
    if lhs.tzinfo is not None and rhs.tzinfo is None:
        rhs = rhs.tz_localize(lhs.tzinfo)
    elif lhs.tzinfo is None and rhs.tzinfo is not None:
        lhs = lhs.tz_localize(rhs.tzinfo)
    return float((lhs - rhs).total_seconds())
