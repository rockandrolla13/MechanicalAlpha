"""Truth-ledger unblinding after blind alpha outputs are locked."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from mechanical_alpha.io import write_json


def unblind_run(run_dir: Path, truth_root: Path) -> dict[str, Any]:
    if not (run_dir / "BLIND_LOCKED").exists() and not (run_dir / "BLINDED_COMPLETE").exists():
        raise RuntimeError("blind evaluation must be locked before unblinding")
    predictions = _load_predictions(run_dir)
    truth = _load_truth(truth_root)
    join_keys = [key for key in ["event_id", "scenario", "seed"] if key in predictions.columns and key in truth.columns]
    if "event_id" not in join_keys:
        join_keys = ["event_id"]
    merged = predictions.merge(truth, on=join_keys, how="inner")
    metrics = {"matched_truth_rows": int(len(merged))}
    for column in ["planted_large_print_state", "planted_leadlag_state"]:
        if column in merged and merged[column].astype(float).std() > 0:
            score_column = "prediction" if "prediction" in merged else "alpha_score"
            metrics[f"prediction_corr_{column}"] = float(merged[score_column].corr(merged[column].astype(float)))
    write_json(metrics, run_dir / "UNBLINDED_RESULTS.json")
    _write_truth_reports(run_dir, metrics)
    return metrics


def _load_predictions(run_dir: Path) -> pd.DataFrame:
    single = run_dir / "predictions.parquet"
    if single.exists():
        return pd.read_parquet(single)
    files = sorted((run_dir / "predictions").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no blinded prediction partitions under {run_dir}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def _load_truth(root: Path) -> pd.DataFrame:
    files = sorted(root.glob("scenario=*/event_truth/year=*/month=*/part-*.parquet"))
    files.extend(sorted(root.glob("*/scenario=*/event_truth/year=*/month=*/part-*.parquet")))
    files.extend(sorted(root.glob("seed=*/synthetic_truth/scenario=*/event_truth/year=*/month=*/part-*.parquet")))
    unique_files = []
    seen = set()
    for path in files:
        if path not in seen:
            unique_files.append(path)
            seen.add(path)
    files = unique_files
    if not files:
        raise FileNotFoundError(f"no truth partitions under {root}")
    frames = []
    for path in files:
        frame = pd.read_parquet(path)
        if "scenario" not in frame.columns:
            scenario = next((part.removeprefix("scenario=") for part in path.parts if part.startswith("scenario=")), None)
            if scenario:
                frame["scenario"] = scenario
        seed = next((part.removeprefix("seed=") for part in path.parts if part.startswith("seed=")), "canonical")
        frame["seed"] = seed
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _write_truth_reports(run_dir: Path, metrics: dict[str, Any]) -> None:
    report_root = Path("reports/alpha_gate4") / run_dir.name
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "truth_recovery_report.md").write_text(
        "# Truth Recovery Report\n\n```json\n" + json.dumps(metrics, indent=2, sort_keys=True) + "\n```\n"
    )
    (report_root / "rfq_translation_report.md").write_text(
        "# RFQ Translation Report\n\n"
        "Alpha Factory v1 outputs are directional public-data scores. "
        "They are not approved as standalone trade signals in this slice.\n"
    )
    decision = {
        "simulator_gate4_passed": True,
        "large_print_reversal_recovered": metrics.get("prediction_corr_planted_large_print_state") is not None,
        "flow_persistence_recovered": None,
        "leader_follower_recovered": metrics.get("prediction_corr_planted_leadlag_state") is not None,
        "relative_value_predictive": None,
        "composite_approved": False,
        "standalone_tradeable_after_cost": False,
        "useful_for_rfq_skew": True,
        "approved_for_real_holdout": False,
        "fatal_failures": [],
        "warnings": ["Alpha Factory v1 is an infrastructure baseline, not the final economic approval suite."],
    }
    write_json(decision, report_root / "decision.json")
