"""Medium-scale validation orchestration for Gate 3."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from bondsim.calibration.frozen import FrozenCalibrationBundle, load_frozen_calibration
from bondsim.config import BondSimConfig
from bondsim.io import write_json, write_parquet
from bondsim.pipeline import SimulationPipeline, _read_partitioned
from bondsim.validation.recovery import (
    oracle_large_print_reversal_target,
    run_oracle_accounting_checks,
    run_public_recovery_checks,
)


GATE3_SCENARIOS = [
    "calibrated_realism",
    "controlled_all",
    "controlled_null",
    "reversal_only",
    "sign_only",
    "leadlag_only",
]


def run_medium_gate(config: BondSimConfig, force: bool = False) -> dict[str, Any]:
    """Run Gate 3 medium simulations, validations, and aggregate reports."""

    if not config.frozen_calibration_id:
        raise RuntimeError("Gate 3 requires frozen_calibration_id")
    frozen = load_frozen_calibration(config.frozen_calibration_id, config.paths.model_root)
    seeds = [config.project.master_seed + idx for idx in range(5)]
    report_root = config.paths.report_root / "gate3"
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "fidelity").mkdir(parents=True, exist_ok=True)
    (report_root / "plot_data").mkdir(parents=True, exist_ok=True)
    (report_root / "figures").mkdir(parents=True, exist_ok=True)
    real_events = pd.read_parquet(config.paths.processed_root / "events.parquet")
    real_test = real_events[real_events.get("split", "test").eq("test")] if "split" in real_events else real_events.tail(max(1, len(real_events) // 6))
    recovery_rows: list[dict[str, Any]] = []
    null_rows: list[dict[str, Any]] = []
    oracle_rows: list[dict[str, Any]] = []
    fidelity_rows: list[dict[str, Any]] = []
    risk_findings: list[str] = []
    for seed in seeds:
        for scenario in GATE3_SCENARIOS:
            run_config = copy.deepcopy(config)
            run_config.project.master_seed = int(seed)
            run_config.paths.synthetic_root = Path("data/medium") / f"seed={seed}" / "synthetic"
            run_config.paths.truth_root = Path("data/medium") / f"seed={seed}" / "synthetic_truth"
            run_config.paths.report_root = Path("reports/medium_runs") / f"seed={seed}" / scenario
            public_root = run_config.paths.synthetic_root / f"scenario={scenario}"
            manifest_path = public_root / "manifest.json"
            if manifest_path.exists() and not force:
                manifest = None
            else:
                manifest = SimulationPipeline(run_config).run(mode="medium", scenario=scenario, force=force)
                _annotate_manifest(manifest.manifest_path, frozen)
                _annotate_manifest(run_config.paths.truth_root / f"scenario={scenario}" / "manifest.json", frozen)
            public = _read_partitioned(run_config.paths.synthetic_root / f"scenario={scenario}" / "trades")
            truth = _read_partitioned(run_config.paths.truth_root / f"scenario={scenario}" / "event_truth")
            public_recovery = run_public_recovery_checks(public)
            oracle = run_oracle_accounting_checks(truth)
            reversal_target = oracle_large_print_reversal_target(
                public,
                truth,
                reversal_amplitude=float(config.positive_controls["large_print_reversal"]["default_amplitude_price_points"]),
            )
            oracle_rows.append(
                {
                    "seed": seed,
                    "scenario": scenario,
                    "metric": reversal_target.name,
                    "estimate": reversal_target.estimate,
                    "expected_sign": reversal_target.expected_sign,
                    "n": reversal_target.n,
                    "passed_direction": reversal_target.passed,
                    "detail": reversal_target.detail,
                }
            )
            for result in public_recovery["results"]:
                row = {
                    "seed": seed,
                    "scenario": scenario,
                    "metric": result["name"],
                    "estimate": result["estimate"],
                    "expected_sign": result["expected_sign"],
                    "n": result["n"],
                    "passed_direction": result["passed"],
                }
                if "null" in result["name"] or result["name"] in {"public_follower_to_leader", "public_cross_issuer"}:
                    null_rows.append(row)
                else:
                    recovery_rows.append(row)
            fidelity_rows.append(
                {
                    "seed": seed,
                    "scenario": scenario,
                    **_fidelity_metrics(real_test, public, truth),
                    "oracle_accounting_passed": oracle["passed"],
                    "oracle_failures": "; ".join(oracle["failures"]),
                    "manifest_path": str(manifest.manifest_path if manifest is not None else manifest_path),
                    "calibration_id": frozen.calibration_id,
                }
            )
            if not oracle["passed"]:
                risk_findings.append(f"{seed} {scenario}: oracle accounting failed: {oracle['failures']}")
    recovery = pd.DataFrame(recovery_rows)
    nulls = pd.DataFrame(null_rows)
    oracle_effects = pd.DataFrame(oracle_rows)
    fidelity = pd.DataFrame(fidelity_rows)
    recovery.to_csv(report_root / "recovery_across_seeds.csv", index=False)
    nulls.to_csv(report_root / "null_controls_across_seeds.csv", index=False)
    oracle_effects.to_csv(report_root / "oracle_effect_targets.csv", index=False)
    fidelity.to_csv(report_root / "medium_fidelity_metrics.csv", index=False)
    write_parquet(recovery, report_root / "plot_data" / "recovery_across_seeds.parquet")
    write_parquet(nulls, report_root / "plot_data" / "null_controls_across_seeds.parquet")
    write_parquet(oracle_effects, report_root / "plot_data" / "oracle_effect_targets.parquet")
    write_parquet(fidelity, report_root / "plot_data" / "medium_fidelity_metrics.parquet")
    gate = _gate_decision(recovery, nulls, fidelity, frozen, oracle_effects)
    _write_medium_reports(report_root, fidelity, recovery, nulls, gate, risk_findings, frozen, oracle_effects)
    return gate


def _fidelity_metrics(real: pd.DataFrame, synthetic: pd.DataFrame, truth: pd.DataFrame) -> dict[str, float]:
    real_rates = real.groupby("source_bond_id")["event_id"].count() / max(real["session_date"].nunique(), 1)
    synth_rates = synthetic.groupby("synthetic_bond_id")["event_id"].count() / max(synthetic["session_date"].nunique(), 1)
    real_zero = _zero_trade_rate(real, "source_bond_id")
    synth_zero = _zero_trade_rate(synthetic, "synthetic_bond_id")
    real_intraday = real["intraday_bucket"].value_counts(normalize=True).sort_index() if "intraday_bucket" in real else pd.Series(dtype=float)
    synth_intraday = (pd.to_datetime(synthetic["timestamp_utc"]).dt.hour * 2).value_counts(normalize=True).sort_index()
    side_balance_real = float(real["side"].mean()) if "side" in real else np.nan
    side_balance_synth = float(synthetic["side"].mean())
    return {
        "real_bond_rate_median": float(real_rates.quantile(0.50)) if len(real_rates) else np.nan,
        "synth_bond_rate_median": float(synth_rates.quantile(0.50)) if len(synth_rates) else np.nan,
        "real_zero_trade_day_rate": real_zero,
        "synth_zero_trade_day_rate": synth_zero,
        "intraday_l1": _l1(real_intraday, synth_intraday),
        "real_side_mean": side_balance_real,
        "synth_side_mean": side_balance_synth,
        "real_run_length_mean": _run_length_mean(real, "source_bond_id"),
        "synth_run_length_mean": _run_length_mean(synthetic, "synthetic_bond_id"),
        "real_notional_p90": float(real["notional"].quantile(0.90)) if "notional" in real else np.nan,
        "synth_notional_p90": float(synthetic["notional"].quantile(0.90)),
        "real_notional_p99": float(real["notional"].quantile(0.99)) if "notional" in real else np.nan,
        "synth_notional_p99": float(synthetic["notional"].quantile(0.99)),
        "real_interdealer_rate": float(real["is_interdealer"].mean()) if "is_interdealer" in real else np.nan,
        "synth_interdealer_rate": float(synthetic["is_interdealer"].mean()),
        "synthetic_concession_std": float(truth["transaction_concession"].astype(float).std()),
        "synthetic_residual_vol": float(synthetic.groupby("synthetic_bond_id")["price"].diff().std()),
        "synthetic_price_autocorr": _mean_autocorr(synthetic, "synthetic_bond_id", "price"),
        "issuer_comovement": _issuer_comovement(synthetic),
    }


def _gate_decision(
    recovery: pd.DataFrame,
    nulls: pd.DataFrame,
    fidelity: pd.DataFrame,
    frozen: FrozenCalibrationBundle,
    oracle_effects: pd.DataFrame | None = None,
) -> dict[str, Any]:
    controlled = recovery[recovery["scenario"].eq("controlled_all")]
    controlled_oracle = (
        oracle_effects[oracle_effects["scenario"].eq("controlled_all")]
        if oracle_effects is not None and not oracle_effects.empty
        else pd.DataFrame()
    )
    intended = {}
    for metric, expected in {
        "public_reversal": -1,
        "sign_persistence": 1,
        "public_leader_to_follower": 1,
    }.items():
        rows = controlled[controlled["metric"].eq(metric)]
        estimates = pd.to_numeric(rows["estimate"], errors="coerce")
        signs = np.sign(estimates.dropna())
        median_estimate = float(estimates.median()) if len(estimates) else np.nan
        target = _target_magnitude(metric, controlled_oracle)
        magnitude_passed = True
        if target is not None and np.isfinite(median_estimate):
            magnitude_passed = abs(abs(median_estimate) - target) / target <= 0.25
        intended[metric] = {
            "correct_sign_count": int((signs == expected).sum()),
            "median_estimate": median_estimate,
            "n_seeds": int(rows["seed"].nunique()),
            "target_magnitude": target,
            "target_source": _target_source(metric, controlled_oracle),
            "magnitude_passed": bool(magnitude_passed),
        }
    null_summary = {}
    controlled_magnitudes = controlled.groupby("metric")["estimate"].apply(lambda s: float(pd.to_numeric(s, errors="coerce").abs().median()))
    for metric in ["public_follower_to_leader", "public_cross_issuer"]:
        rows = nulls[nulls["metric"].eq(metric)]
        estimate = float(pd.to_numeric(rows["estimate"], errors="coerce").abs().median()) if len(rows) else np.nan
        denominator = max(float(controlled_magnitudes.max()) if len(controlled_magnitudes) else 0.0, 1e-12)
        null_summary[metric] = {"median_abs": estimate, "fraction_of_controlled_max": estimate / denominator}
    oracle_passed = bool(fidelity["oracle_accounting_passed"].all()) if "oracle_accounting_passed" in fidelity else False
    passed = oracle_passed and all(item["correct_sign_count"] >= 4 and item["magnitude_passed"] for item in intended.values()) and all(
        value["fraction_of_controlled_max"] < 0.20 for value in null_summary.values() if np.isfinite(value["fraction_of_controlled_max"])
    )
    decision = "PASS" if passed else "FAIL"
    reversal = intended.get("public_reversal", {})
    sign = intended.get("sign_persistence", {})
    leadlag = intended.get("public_leader_to_follower", {})
    return {
        "passed": bool(passed),
        "oracle_accounting_passed": oracle_passed,
        "calibration_id": frozen.calibration_id,
        "gate3_run_id": f"gate3-{frozen.calibration_id}",
        "decision": decision,
        "intended_effects": intended,
        "null_controls": null_summary,
        "reversal": _effect_decision(reversal, null_summary),
        "sign_persistence": _effect_decision(sign, null_summary),
        "leadlag": _leadlag_decision(leadlag, null_summary),
        "fatal_failures": [] if passed else _fatal_failures(intended, null_summary, oracle_passed),
        "warnings": frozen.environment_deviations,
        "approved_for_gate4": bool(passed),
    }


def _write_medium_reports(
    report_root: Path,
    fidelity: pd.DataFrame,
    recovery: pd.DataFrame,
    nulls: pd.DataFrame,
    gate: dict[str, Any],
    risk_findings: list[str],
    frozen: FrozenCalibrationBundle,
    oracle_effects: pd.DataFrame | None = None,
) -> None:
    summary = {
        "gate": gate,
        "fidelity_medians": fidelity.select_dtypes(include=[np.number]).median(numeric_only=True).to_dict(),
        "recovery_medians": _string_key_dict(recovery.groupby(["scenario", "metric"])["estimate"].median()) if not recovery.empty else {},
        "null_medians": _string_key_dict(nulls.groupby(["scenario", "metric"])["estimate"].median()) if not nulls.empty else {},
        "oracle_target_medians": _string_key_dict(oracle_effects.groupby(["scenario", "metric"])["estimate"].median())
        if oracle_effects is not None and not oracle_effects.empty
        else {},
    }
    (report_root / "gate3_summary.md").write_text("# Gate 3 Summary\n\n```json\n" + json.dumps(summary, indent=2, default=str) + "\n```\n")
    write_json(summary, report_root / "gate3_summary.json")
    write_json(gate, report_root / "GATE3_DECISION.json")
    (report_root / "index.html").write_text(_gate3_html(gate, frozen))
    _write_compatibility_reports(report_root, fidelity, recovery, nulls)
    findings = risk_findings.copy()
    if not gate["passed"]:
        findings.append("Gate 3 did not pass the predefined recovery/null-control criteria.")
    if not findings:
        findings.append("No oracle accounting or leakage failures were detected. Statistical gates are reported separately.")
    (report_root / "model_risk_findings.md").write_text("# Model Risk Findings\n\n" + "\n".join(f"- {item}" for item in findings) + "\n")


def _target_magnitude(metric: str, controlled_oracle: pd.DataFrame) -> float | None:
    if metric == "public_reversal" and not controlled_oracle.empty:
        rows = controlled_oracle[controlled_oracle["metric"].eq("oracle_reversal_target")]
        if not rows.empty:
            value = float(pd.to_numeric(rows["estimate"], errors="coerce").abs().median())
            if np.isfinite(value) and value > 0.0:
                return value
    return {"public_reversal": 0.06, "public_leader_to_follower": 0.05}.get(metric)


def _target_source(metric: str, controlled_oracle: pd.DataFrame) -> str | None:
    if metric == "public_reversal" and not controlled_oracle.empty:
        rows = controlled_oracle[controlled_oracle["metric"].eq("oracle_reversal_target")]
        if not rows.empty and pd.to_numeric(rows["estimate"], errors="coerce").notna().any():
            return "truth-ledger realized large-print state contribution"
    if metric in {"public_reversal", "public_leader_to_follower"}:
        return "configured unit-size default"
    return None
    return None


def _annotate_manifest(path: Path, frozen: FrozenCalibrationBundle) -> None:
    payload = json.loads(path.read_text())
    payload["frozen_calibration_id"] = frozen.calibration_id
    payload["frozen_calibration_path"] = str(frozen.path)
    payload["frozen_source_fingerprint"] = frozen.source_fingerprint_hash
    payload["frozen_resolved_config_hash"] = frozen.resolved_config_hash
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _effect_decision(effect: dict[str, Any], null_summary: dict[str, Any]) -> dict[str, Any]:
    n_seeds = max(int(effect.get("n_seeds", 0)), 1)
    target = effect.get("target_magnitude")
    estimate = abs(float(effect.get("median_estimate", np.nan)))
    relative_error = abs(estimate - target) / target if target and np.isfinite(estimate) else np.nan
    null_fraction = max((item.get("fraction_of_controlled_max", 0.0) for item in null_summary.values()), default=np.nan)
    return {
        "sign_success_rate": float(effect.get("correct_sign_count", 0)) / n_seeds,
        "median_relative_error": relative_error,
        "null_fraction": null_fraction,
        "passed": bool(effect.get("correct_sign_count", 0) >= 4 and effect.get("magnitude_passed", False)),
    }


def _leadlag_decision(effect: dict[str, Any], null_summary: dict[str, Any]) -> dict[str, Any]:
    row = _effect_decision(effect, null_summary)
    row["reverse_control_fraction"] = null_summary.get("public_follower_to_leader", {}).get("fraction_of_controlled_max", np.nan)
    row["cross_issuer_control_fraction"] = null_summary.get("public_cross_issuer", {}).get("fraction_of_controlled_max", np.nan)
    return row


def _fatal_failures(intended: dict[str, Any], null_summary: dict[str, Any], oracle_passed: bool) -> list[str]:
    failures = []
    if not oracle_passed:
        failures.append("oracle accounting failed")
    for name, effect in intended.items():
        if effect.get("correct_sign_count", 0) < 4:
            failures.append(f"{name} sign success below 4 of 5 seeds")
        if not effect.get("magnitude_passed", False):
            failures.append(f"{name} magnitude recovery outside tolerance")
    for name, value in null_summary.items():
        if value.get("fraction_of_controlled_max", 0.0) >= 0.20:
            failures.append(f"{name} null control above 20 percent threshold")
    return failures


def _gate3_html(gate: dict[str, Any], frozen: FrozenCalibrationBundle) -> str:
    return (
        "<html><body>"
        f"<h1>Gate 3 {gate['decision']}</h1>"
        f"<p>Frozen calibration: <code>{frozen.calibration_id}</code></p>"
        f"<p>Approved for Gate 4: <code>{gate['approved_for_gate4']}</code></p>"
        "<p>Plot data live under <code>reports/gate3/plot_data</code>.</p>"
        "</body></html>\n"
    )


def _write_compatibility_reports(report_root: Path, fidelity: pd.DataFrame, recovery: pd.DataFrame, nulls: pd.DataFrame) -> None:
    (report_root / "medium_validation.md").write_text("# Medium Validation\n\nSee `gate3_summary.md` for the locked Gate 3 report.\n")
    (report_root / "fidelity" / "medium_summary.md").write_text(
        "# Medium Fidelity Summary\n\n```text\n"
        + fidelity.groupby("scenario").median(numeric_only=True).to_string()
        + "\n```\n"
    )


def _zero_trade_rate(frame: pd.DataFrame, bond_col: str) -> float:
    if frame.empty:
        return np.nan
    counts = frame.groupby([bond_col, "session_date"]).size()
    sessions = frame["session_date"].nunique()
    bonds = frame[bond_col].nunique()
    observed = len(counts)
    return float(1.0 - observed / max(sessions * bonds, 1))


def _run_length_mean(frame: pd.DataFrame, bond_col: str) -> float:
    if frame.empty or "side" not in frame:
        return np.nan
    ordered = frame.sort_values(["timestamp_utc", bond_col])
    lengths = []
    for _, group in ordered.groupby(bond_col):
        run = 0
        prev = None
        for side in group["side"]:
            run = run + 1 if side == prev else 1
            lengths.append(run)
            prev = side
    return float(np.mean(lengths)) if lengths else np.nan


def _l1(left: pd.Series, right: pd.Series) -> float:
    aligned = left.subtract(right, fill_value=0.0).abs()
    return float(aligned.sum())


def _mean_autocorr(frame: pd.DataFrame, bond_col: str, value_col: str) -> float:
    values = []
    for _, group in frame.sort_values("timestamp_utc").groupby(bond_col):
        series = group[value_col].astype(float)
        if len(series) > 2:
            values.append(series.autocorr())
    values = [value for value in values if np.isfinite(value)]
    return float(np.mean(values)) if values else np.nan


def _issuer_comovement(frame: pd.DataFrame) -> float:
    daily = frame.assign(price_change=frame.groupby("synthetic_bond_id")["price"].diff()).pivot_table(
        index="session_date",
        columns="synthetic_issuer_id",
        values="price_change",
        aggfunc="mean",
    )
    if daily.shape[1] < 2:
        return np.nan
    corr = daily.corr().to_numpy()
    mask = ~np.eye(corr.shape[0], dtype=bool)
    values = corr[mask]
    values = values[np.isfinite(values)]
    return float(values.mean()) if len(values) else np.nan


def _string_key_dict(series: pd.Series) -> dict[str, float]:
    result = {}
    for key, value in series.to_dict().items():
        if isinstance(key, tuple):
            name = " / ".join(str(part) for part in key)
        else:
            name = str(key)
        result[name] = float(value) if pd.notna(value) else np.nan
    return result
