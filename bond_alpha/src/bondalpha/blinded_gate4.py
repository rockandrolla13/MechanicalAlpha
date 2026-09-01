"""Strictly blinded Gate 4 alpha evaluation.

The evaluator reads only two inputs:

- a frozen alpha specification;
- released Gate 4 public synthetic trade partitions.

It deliberately does not load Gate 4 truth roots, simulator truth parameters,
latent-state columns, or controlled-effect configuration.
"""

from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from bondalpha.access_guard import assert_no_truth_columns, assert_public_path
from bondalpha.features import build_features
from bondalpha.freeze import load_frozen_model, verify_checksums
from bondalpha.labels import add_public_labels
from bondalpha.models.linear import predict_proba
from bondsim.io import write_json, write_parquet
from bondsim.utils.hashing import file_sha256, stable_json_hash


REQUIRED_SCENARIOS = {
    "calibrated_realism",
    "controlled_all",
    "controlled_null",
    "reversal_only",
    "sign_only",
    "leadlag_only",
}


@dataclass(frozen=True)
class PublicScenario:
    scenario: str
    root: Path
    manifest_path: Path
    trade_paths: tuple[Path, ...]
    bond_path: Path
    rows: int
    seed: str


def run_strict_blinded_gate4_evaluation(
    alpha_spec_root: Path,
    public_root: Path,
    *,
    output_root: Path = Path("runs/alpha_gate4"),
    force: bool = False,
) -> dict[str, Any]:
    """Run the frozen alpha model against released Gate 4 public data."""

    alpha_manifest, fitted = load_frozen_model(alpha_spec_root)
    alpha_spec_manifest = _alpha_spec_manifest(alpha_spec_root, alpha_manifest)
    scenarios = _load_public_scenarios(public_root, alpha_spec_root.name)
    public_manifest = _public_data_manifest(public_root, scenarios)
    run_id = _run_id(alpha_spec_manifest, public_manifest, alpha_manifest.get("target"))
    run_dir = output_root / run_id
    if run_dir.exists() and (run_dir / "BLINDED_COMPLETE").exists() and not force:
        raise FileExistsError(f"blinded Gate 4 run already exists: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    for child in ("features", "labels", "predictions", "coefficients", "metrics", "plot_data", "figures"):
        (run_dir / child).mkdir(parents=True, exist_ok=True)

    target = str(alpha_manifest["target"])
    horizon = target.removeprefix("future_price_up_")
    metric_rows: list[dict[str, Any]] = []
    partition_rows: list[dict[str, Any]] = []
    prediction_samples: list[pd.DataFrame] = []

    for scenario in scenarios:
        trades = _read_public_trades(scenario.trade_paths, scenario.scenario)
        labeled = add_public_labels(trades, [horizon])
        features = build_features(labeled)
        features["seed"] = scenario.seed
        predictions = features[["event_id", "scenario", "timestamp_utc", "synthetic_bond_id"]].copy()
        predictions["seed"] = scenario.seed
        predictions["alpha_score"] = predict_proba(fitted, features)
        predictions["target"] = target
        predictions["alpha_spec_id"] = alpha_spec_root.name
        labels = labeled[["event_id", target]].copy()
        labels["scenario"] = scenario.scenario
        labels["seed"] = scenario.seed

        feature_path = write_parquet(features, run_dir / "features" / f"{scenario.seed}_{scenario.scenario}.parquet")
        label_path = write_parquet(labels, run_dir / "labels" / f"{scenario.seed}_{scenario.scenario}.parquet")
        prediction_path = write_parquet(predictions, run_dir / "predictions" / f"{scenario.seed}_{scenario.scenario}.parquet")
        metrics = _metrics(labeled[target], predictions["alpha_score"])
        metrics.update({"scenario": scenario.scenario, "seed": scenario.seed, "rows": int(len(predictions))})
        metric_rows.append(metrics)
        partition_rows.append(
            {
                "scenario": scenario.scenario,
                "seed": scenario.seed,
                "features": str(feature_path),
                "labels": str(label_path),
                "predictions": str(prediction_path),
                "rows": int(len(predictions)),
                "feature_sha256": file_sha256(feature_path),
                "label_sha256": file_sha256(label_path),
                "prediction_sha256": file_sha256(prediction_path),
            }
        )
        prediction_samples.append(_sample_predictions(predictions, scenario.scenario, scenario.seed))

    metrics_frame = pd.DataFrame(metric_rows).sort_values(["seed", "scenario"]).reset_index(drop=True)
    partition_frame = pd.DataFrame(partition_rows).sort_values(["seed", "scenario"]).reset_index(drop=True)
    _write_report_table(metrics_frame, run_dir / "metrics" / "scenario_metrics.parquet")
    _write_report_table(partition_frame, run_dir / "metrics" / "partition_outputs.parquet")
    coefficients = _coefficients(fitted)
    _write_report_table(coefficients, run_dir / "coefficients" / "model_coefficients.parquet")
    plot_data = pd.concat(prediction_samples, ignore_index=True) if prediction_samples else pd.DataFrame()
    _write_report_table(plot_data, run_dir / "plot_data" / "prediction_score_distribution.parquet")
    _write_score_plot(plot_data, run_dir / "figures" / "prediction_score_distribution.png")

    report = {
        "alpha_gate4_run_id": run_id,
        "locked": True,
        "blinded": True,
        "truth_accessed": False,
        "alpha_spec_id": alpha_spec_root.name,
        "public_root": str(public_root),
        "target": target,
        "horizon": horizon,
        "scenario_count": len(scenarios),
        "total_rows": int(metrics_frame["rows"].sum()) if not metrics_frame.empty else 0,
        "public_data_manifest": "public_data_manifest.json",
        "alpha_spec_manifest": "alpha_spec_manifest.json",
        "metrics": metric_rows,
        "outputs": partition_rows,
        "acceptance": _acceptance(metrics_frame),
    }
    write_json(public_manifest, run_dir / "public_data_manifest.json")
    write_json(alpha_spec_manifest, run_dir / "alpha_spec_manifest.json")
    write_json(report, run_dir / "blinded_report.json")
    (run_dir / "blinded_report.md").write_text(_markdown_report(report, metrics_frame))
    _write_checksums(run_dir)
    (run_dir / "BLINDED_COMPLETE").write_text(run_id + "\n")
    _write_checksums(run_dir)
    return report


def _load_public_scenarios(public_root: Path, alpha_spec_id: str) -> list[PublicScenario]:
    assert_public_path(public_root)
    manifest = _gate4_manifest_for(public_root)
    if manifest and manifest.get("released_to_alpha_spec_id") != alpha_spec_id:
        raise PermissionError(
            f"Gate 4 public data was released to {manifest.get('released_to_alpha_spec_id')}, not {alpha_spec_id}"
        )
    roots = _scenario_roots(public_root)
    scenarios: list[PublicScenario] = []
    for root in roots:
        scenario = root.name.removeprefix("scenario=")
        if scenario not in REQUIRED_SCENARIOS:
            continue
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"public scenario manifest missing: {manifest_path}")
        scenario_manifest = json.loads(manifest_path.read_text())
        trade_paths = tuple(Path(item["path"]) for item in scenario_manifest.get("partitions", {}).get("public", []))
        if not trade_paths:
            trade_paths = tuple(sorted((root / "trades").glob("year=*/month=*/part-*.parquet")))
        _verify_manifest_files(scenario_manifest, trade_paths)
        bond_path = root / "bonds.parquet"
        if not bond_path.exists():
            raise FileNotFoundError(f"public bonds file missing: {bond_path}")
        scenarios.append(
            PublicScenario(
                scenario=scenario,
                root=root,
                manifest_path=manifest_path,
                trade_paths=trade_paths,
                bond_path=bond_path,
                rows=int(scenario_manifest.get("rows", {}).get("public", 0)),
                seed=_seed_for(root),
            )
        )
    found = {scenario.scenario for scenario in scenarios}
    missing = REQUIRED_SCENARIOS - found
    if missing:
        raise RuntimeError(f"released Gate 4 public data missing scenarios: {sorted(missing)}")
    return sorted(scenarios, key=lambda item: (item.seed, item.scenario))


def _gate4_manifest_for(public_root: Path) -> dict[str, Any] | None:
    parts = public_root.parts
    if "gate4" not in parts:
        return None
    idx = parts.index("gate4")
    if idx + 1 >= len(parts):
        return None
    run_id = parts[idx + 1]
    path = Path("runs/gate4") / run_id / "gate4_manifest.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _scenario_roots(public_root: Path) -> list[Path]:
    roots: list[Path] = []
    if public_root.name.startswith("scenario="):
        roots.append(public_root)
    roots.extend(sorted(path for path in public_root.glob("scenario=*") if path.is_dir()))
    roots.extend(sorted(path for path in public_root.glob("seed=*/synthetic/scenario=*") if path.is_dir()))
    seen: set[Path] = set()
    unique = []
    for root in roots:
        if root not in seen:
            unique.append(root)
            seen.add(root)
    return unique


def _verify_manifest_files(manifest: dict[str, Any], trade_paths: tuple[Path, ...]) -> None:
    hash_by_path = {item["path"]: item["sha256"] for item in manifest.get("files", []) if "synthetic_truth" not in item.get("path", "")}
    failures = []
    for path in trade_paths:
        expected = hash_by_path.get(str(path))
        if expected and file_sha256(path) != expected:
            failures.append(str(path))
    if failures:
        raise RuntimeError(f"public-data checksum failures: {failures}")


def _read_public_trades(paths: tuple[Path, ...], scenario: str) -> pd.DataFrame:
    frames = []
    for path in paths:
        assert_public_path(path)
        frame = pd.read_parquet(path)
        assert_no_truth_columns(frame.columns)
        if "scenario" not in frame.columns:
            frame["scenario"] = scenario
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True)
    assert_no_truth_columns(out.columns)
    return out


def _alpha_spec_manifest(spec_root: Path, alpha_manifest: dict[str, Any]) -> dict[str, Any]:
    failures = verify_checksums(spec_root)
    if failures:
        raise RuntimeError(f"alpha-spec checksum failures: {failures}")
    files = [
        {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}
        for path in sorted(spec_root.rglob("*"))
        if path.is_file() and path.name != "checksums.sha256"
    ]
    return {
        "alpha_spec_id": spec_root.name,
        "frozen": True,
        "target": alpha_manifest.get("target"),
        "feature_columns": alpha_manifest.get("feature_columns", []),
        "files": files,
        "checksum_failures": failures,
    }


def _public_data_manifest(public_root: Path, scenarios: list[PublicScenario]) -> dict[str, Any]:
    return {
        "public_root": str(public_root),
        "scenarios": [
            {
                "scenario": item.scenario,
                "seed": item.seed,
                "manifest_path": str(item.manifest_path),
                "trade_partitions": len(item.trade_paths),
                "rows": item.rows,
                "trade_sha256": stable_json_hash([file_sha256(path) for path in item.trade_paths]),
                "bond_sha256": file_sha256(item.bond_path),
            }
            for item in scenarios
        ],
    }


def _metrics(labels: pd.Series, scores: pd.Series) -> dict[str, float | int | None]:
    valid = labels.notna() & scores.notna()
    n = int(valid.sum())
    if n == 0:
        return {"n_labeled": 0, "brier": None, "directional_accuracy": None, "mean_score": float(scores.mean())}
    y = labels[valid].astype(float)
    p = scores[valid].astype(float).clip(1e-6, 1 - 1e-6)
    brier = float(np.mean((p - y) ** 2))
    acc = float(np.mean((p >= 0.5) == (y >= 0.5)))
    return {"n_labeled": n, "brier": brier, "directional_accuracy": acc, "mean_score": float(scores.mean())}


def _coefficients(fitted: Any) -> pd.DataFrame:
    model = fitted.model
    estimator = model.steps[-1][1] if hasattr(model, "steps") else model
    coef = getattr(estimator, "coef_", np.zeros((1, len(fitted.feature_columns))))[0]
    return pd.DataFrame({"feature": fitted.feature_columns, "coefficient": coef.astype(float)})


def _sample_predictions(predictions: pd.DataFrame, scenario: str, seed: str, n: int = 5000) -> pd.DataFrame:
    if len(predictions) <= n:
        sample = predictions.copy()
    else:
        hashes = predictions["event_id"].astype(str).map(lambda value: int(stable_json_hash(value)[:16], 16))
        sample = predictions.loc[hashes.rank(method="first") <= n].copy()
    sample["scenario"] = scenario
    sample["seed"] = seed
    return sample[["scenario", "seed", "alpha_score"]]


def _write_score_plot(plot_data: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 4.5))
    if plot_data.empty:
        plt.text(0.5, 0.5, "No predictions", ha="center", va="center")
    else:
        for scenario, group in plot_data.groupby("scenario"):
            plt.hist(group["alpha_score"], bins=np.linspace(0, 1, 31), alpha=0.35, label=scenario)
        plt.xlabel("Frozen alpha score")
        plt.ylabel("Sampled event count")
        plt.title("Blinded Gate 4 score distribution")
        plt.legend(fontsize=7)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _write_report_table(frame: pd.DataFrame, path: Path) -> Path:
    """Write small audit/report tables in a conservative Parquet encoding."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pandas(frame.reset_index(drop=True), preserve_index=False)
    pq.write_table(table, tmp, compression=None, version="1.0", use_dictionary=False)
    tmp.replace(path)
    return path


def _acceptance(metrics: pd.DataFrame) -> dict[str, Any]:
    if metrics.empty:
        return {"decision": "FAIL", "failures": ["no metrics"]}
    failures = []
    if metrics["rows"].le(0).any():
        failures.append("one or more scenario evaluations produced no rows")
    if metrics["mean_score"].isna().any():
        failures.append("one or more scenarios produced invalid scores")
    return {"decision": "PASS" if not failures else "FAIL", "failures": failures}


def _markdown_report(report: dict[str, Any], metrics: pd.DataFrame) -> str:
    lines = [
        "# Blinded Gate 4 Alpha Evaluation",
        "",
        f"- run_id: `{report['alpha_gate4_run_id']}`",
        f"- alpha_spec_id: `{report['alpha_spec_id']}`",
        f"- public_root: `{report['public_root']}`",
        f"- target: `{report['target']}`",
        f"- truth_accessed: `{report['truth_accessed']}`",
        f"- decision: `{report['acceptance']['decision']}`",
        "",
        "## Scenario Metrics",
        "",
    ]
    if metrics.empty:
        lines.append("No metrics were produced.")
    else:
        for row in metrics.to_dict(orient="records"):
            lines.append(
                f"- {row['seed']} / {row['scenario']}: rows `{row['rows']}`, labeled `{row['n_labeled']}`, "
                f"brier `{_fmt(row['brier'])}`, accuracy `{_fmt(row['directional_accuracy'])}`"
            )
    return "\n".join(lines) + "\n"


def _fmt(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{float(value):.6f}"


def _run_id(alpha_manifest: dict[str, Any], public_manifest: dict[str, Any], target: str | None) -> str:
    return "alpha-gate4-" + stable_json_hash({"alpha": alpha_manifest, "public": public_manifest, "target": target})[:16]


def _seed_for(root: Path) -> str:
    for part in root.parts:
        if part.startswith("seed="):
            return part.removeprefix("seed=")
    return "canonical"


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")
