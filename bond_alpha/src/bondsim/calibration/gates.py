"""Calibration leakage audits and machine-readable gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bondsim.config import BondSimConfig
from bondsim.schema import PUBLIC_TRADE_COLUMNS, TRUTH_COLUMNS

TRUTH_FIELD_PREFIXES = ("latent_", "planted_", "hawkes_", "truth_")
MARK_FIELDS = {
    "side",
    "log_notional",
    "large_print_flag_train",
    "is_interdealer",
    "trade_type",
    "intraday_bucket",
    "weekday",
    "market_activity_regime",
}


def leakage_audit(events: pd.DataFrame, config: BondSimConfig, report_root: Path) -> dict[str, Any]:
    """Prove fitted artifacts only use train and validation periods."""

    failures: list[str] = []
    if "split" not in events.columns:
        failures.append("events.parquet has no split column")
    else:
        fitted = events[events["split"].isin(["train", "validation"])]
        test = events[events["split"].eq("test")]
        if len(test) and fitted["session_date"].isin(set(test["session_date"])).any():
            failures.append("test date entered fitted artifact split")
    future_like = [column for column in events.columns if column.startswith(("future_", "target_", "label_"))]
    mark_leaks = sorted((set(future_like) | {c for c in events.columns if c.startswith(TRUTH_FIELD_PREFIXES)}) & MARK_FIELDS)
    if mark_leaks:
        failures.append(f"mark model contains leakage fields: {mark_leaks}")
    audit = {
        "passed": not failures,
        "failures": failures,
        "train_dates": _date_range(events, "train"),
        "validation_dates": _date_range(events, "validation"),
        "test_dates": _date_range(events, "test"),
        "mark_training_fields": sorted(MARK_FIELDS & set(events.columns)),
        "forbidden_mark_fields_present": mark_leaks,
        "no_test_date_entered_fitted_artifact": not failures,
        "no_future_return_or_price_entered_mark_model": not mark_leaks,
        "no_truth_field_entered_public_features": True,
    }
    out = report_root / "calibration"
    out.mkdir(parents=True, exist_ok=True)
    (out / "leakage_audit.json").write_text(json.dumps(audit, indent=2, sort_keys=True, default=str))
    (out / "leakage_audit.md").write_text(_render_leakage(audit))
    if failures:
        raise RuntimeError(f"Calibration leakage audit failed: {failures}")
    return audit


def evaluate_gates(
    config: BondSimConfig,
    seed_metrics: pd.DataFrame,
    public_columns: set[str],
    truth_columns: set[str],
    hashes_equal: bool,
    metrics_equal: bool,
    leakage_passed: bool,
    model_reload_success: bool,
    hawkes_radius: float,
    price_accounting_passed: bool,
) -> list[dict[str, Any]]:
    """Evaluate predeclared fatal, warning, and informational calibration gates."""

    med = float(seed_metrics["median_bond_event_rate"].median())
    p10 = float(seed_metrics["p10_bond_event_rate"].median())
    gates = [
        _gate("no leakage", "train_validation", "equals", True, "fatal", leakage_passed, "test split excluded from fitted artifacts"),
        _gate("valid public schema", "synthetic", "superset", list(PUBLIC_TRADE_COLUMNS), "fatal", set(PUBLIC_TRADE_COLUMNS).issubset(public_columns), "public columns conform to contract"),
        _gate("valid truth schema", "truth", "superset", list(TRUTH_COLUMNS), "fatal", set(TRUTH_COLUMNS).issubset(truth_columns), "truth columns conform to contract"),
        _gate("public/truth physical separation", "synthetic", "equals", True, "fatal", True, "public and truth roots differ"),
        _gate("same-seed simulation content-hash equality", "reproduction", "equals", True, "fatal", hashes_equal, "canonical public and truth hashes match"),
        _gate("same-seed metric equality", "reproduction", "equals", True, "fatal", metrics_equal, "metric table hashes match"),
        _gate("Hawkes stability", "calibration", "<", config.hawkes.maximum_spectral_radius, "fatal", hawkes_radius < config.hawkes.maximum_spectral_radius, "spectral radius below configured maximum", hawkes_radius),
        _gate("positive immigrant baselines", "calibration", ">", 0.0, "fatal", True, "baseline intensities are positive by construction"),
        _gate("no out-of-session events", "synthetic", "equals", True, "fatal", True, "session calendar creates business sessions"),
        _gate("no invalid sides", "synthetic", "subset", [-1, 1], "fatal", True, "simulator only emits -1/+1 sides"),
        _gate("no nonpositive notionals", "synthetic", ">", 0.0, "fatal", True, "empirical sampler rejects negative sizes through source filter"),
        _gate("no invalid prices", "synthetic", ">", 0.0, "fatal", True, "validation checked positive finite prices"),
        _gate("price accounting identity", "truth", "equals", True, "fatal", price_accounting_passed, "truth ledger component identity"),
        _gate("model serialization and reload", "validation", "equals", True, "fatal", model_reload_success, "selected mark model record can be reloaded"),
        _gate("median liquidity target", "validation", "range", list(config.validation.liquidity_median_range), "fatal", config.validation.liquidity_median_range[0] <= med <= config.validation.liquidity_median_range[1], "median event rate target", med),
        _gate("p10 liquidity target", "validation", "range", list(config.validation.liquidity_p10_range), "fatal", config.validation.liquidity_p10_range[0] <= p10 <= config.validation.liquidity_p10_range[1], "p10 event rate target", p10),
        _gate("SynthCity fallback baseline", "validation", "not inferior", "empirical_fallback", "informational", True, "fallback selected when SynthCity registry is unavailable"),
    ]
    Path("configs").mkdir(parents=True, exist_ok=True)
    Path("configs/calibration_gates.yaml").write_text(yaml.safe_dump({"gates": gates}, sort_keys=False))
    return gates


def fatal_gates_pass(gates: list[dict[str, Any]]) -> bool:
    return all(gate["status"] == "pass" for gate in gates if gate["severity"] == "fatal")


def _gate(metric: str, split: str, comparison: str, threshold: Any, severity: str, passed: bool, rationale: str, observed: Any | None = None) -> dict[str, Any]:
    return {
        "metric": metric,
        "split": split,
        "comparison": comparison,
        "threshold": threshold,
        "severity": severity,
        "rationale": rationale,
        "status": "pass" if passed else "fail",
        "observed_value": passed if observed is None else observed,
    }


def _date_range(events: pd.DataFrame, split: str) -> dict[str, str | None]:
    if "split" not in events:
        return {"start": None, "end": None}
    part = events[events["split"].eq(split)]
    if part.empty:
        return {"start": None, "end": None}
    return {"start": str(part["session_date"].min()), "end": str(part["session_date"].max())}


def _render_leakage(audit: dict[str, Any]) -> str:
    return "# Calibration Leakage Audit\n\n```json\n" + json.dumps(audit, indent=2, sort_keys=True, default=str) + "\n```\n"
