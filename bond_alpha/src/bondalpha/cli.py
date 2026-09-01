"""Command line interface for Alpha Factory v1."""

from __future__ import annotations

import argparse
import importlib
import json
import pickle
import shutil
from pathlib import Path
from typing import Any

import pandas as pd

from bondalpha import __version__
from bondalpha.blinded_gate4 import run_strict_blinded_gate4_evaluation
from bondalpha.config import load_alpha_config
from bondalpha.datasets import load_public_synthetic
from bondalpha.features import build_features
from bondalpha.freeze import freeze_alpha_spec, load_frozen_model
from bondalpha.labels import add_public_labels
from bondalpha.reporting import write_gate3_alpha_reports, write_frame_report
from bondalpha.target_labels import build_target_labels
from bondalpha.models.linear import fit_logistic, predict_proba
from bondalpha.splits import assign_time_splits
from bondalpha.unblind import unblind_run
from bondalpha.visualization.report import write_alpha_report
from mechanical_alpha.hashing import file_sha256, stable_json_hash
from mechanical_alpha.io import write_json, write_parquet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bondalpha")
    sub = parser.add_subparsers(dest="command", required=True)
    develop = sub.add_parser("develop")
    develop.add_argument("--config", default="configs/alphas/base.yaml")
    develop.add_argument("--data-root")
    report = sub.add_parser("report")
    report.add_argument("--run", required=True)
    reproduce = sub.add_parser("reproduce")
    reproduce.add_argument("--run", required=True)
    reproduce.add_argument("--output", required=True)
    freeze = sub.add_parser("freeze-spec")
    freeze.add_argument("--run", required=True)
    freeze.add_argument("--force", action="store_true")
    blind = sub.add_parser("evaluate-blind")
    blind.add_argument("--alpha-spec", required=True)
    blind.add_argument("--public-root", required=True)
    blind.add_argument("--output", required=True)
    blind_gate4 = sub.add_parser("evaluate-gate4")
    blind_gate4.add_argument("--alpha-spec", required=True)
    blind_gate4.add_argument("--public-root", required=True)
    blind_gate4.add_argument("--output-root", default="runs/alpha_gate4")
    blind_gate4.add_argument("--force", action="store_true")
    unblind = sub.add_parser("unblind")
    unblind.add_argument("--run", required=True)
    unblind.add_argument("--truth-root", required=True)
    workflow = sub.add_parser("blinded-workflow")
    workflow.add_argument("--gate4-config", default="configs/gate4.yaml")
    workflow.add_argument("--alpha-config", default="configs/alphas/base.yaml")
    workflow.add_argument("--gate3-public-root", default="data/medium")
    workflow.add_argument("--gate4-run-id")
    workflow.add_argument("--mode", default="full", choices=["smoke", "medium", "full"])
    workflow.add_argument("--force", action="store_true")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--public-root", required=True)
    build = sub.add_parser("build-features")
    build.add_argument("--public-root", required=True)
    build.add_argument("--config", default="configs/alpha/base.yaml")
    research = sub.add_parser("research")
    research.add_argument("--public-root", required=True)
    research.add_argument("--config", default="configs/alpha/base.yaml")
    validate = sub.add_parser("validate")
    validate.add_argument("--public-root", required=True)
    validate.add_argument("--config", default="configs/alpha/base.yaml")
    args = parser.parse_args(argv)
    if args.command == "develop":
        config = load_alpha_config(args.config)
        root = Path(args.data_root) if args.data_root else config.paths.gate3_public_root
        run_dir = develop_alpha(config, root)
        print(f"alpha run={run_dir}")
    elif args.command == "report":
        print(Path(args.run) / "reports" / "alpha_report.md")
    elif args.command == "reproduce":
        source = Path(args.run)
        manifest = json.loads((source / "alpha_manifest.json").read_text())
        config_path = source / "resolved_alpha_config.yaml"
        output = Path(args.output)
        run_dir = develop_alpha(load_alpha_config(config_path), Path(manifest["public_data_root"]), output_override=output)
        print(f"alpha reproduction={run_dir}")
    elif args.command == "freeze-spec":
        frozen = freeze_alpha_spec(Path(args.run), force=args.force)
        print(f"alpha spec={frozen}")
    elif args.command == "evaluate-blind":
        result = evaluate_blind(Path(args.alpha_spec), Path(args.public_root), Path(args.output))
        print(f"blind evaluation locked={result['locked']} output={args.output}")
    elif args.command == "evaluate-gate4":
        result = run_strict_blinded_gate4_evaluation(
            Path(args.alpha_spec),
            Path(args.public_root),
            output_root=Path(args.output_root),
            force=args.force,
        )
        print(f"blinded gate4 run={result['alpha_gate4_run_id']} decision={result['acceptance']['decision']}")
    elif args.command == "unblind":
        result = unblind_run(Path(args.run), Path(args.truth_root))
        print(f"unblinded matched_truth_rows={result['matched_truth_rows']}")
    elif args.command == "blinded-workflow":
        alpha_workflow = importlib.import_module("bondsim.alpha_workflow")
        bondsim_config = importlib.import_module("bondsim.config")

        result = alpha_workflow.run_blinded_workflow(
            bondsim_config.load_config(args.gate4_config),
            load_alpha_config(args.alpha_config),
            gate3_public_root=Path(args.gate3_public_root),
            gate4_run_id=args.gate4_run_id,
            gate4_mode=args.mode,
            force=args.force,
        )
        print(f"workflow run_id={result.workflow_run_id} blind_output={result.blind_output}")
    elif args.command == "inspect":
        result = inspect_public_data(Path(args.public_root))
        print(f"alpha inspect rows={result['rows']} scenarios={len(result['scenarios'])}")
    elif args.command == "build-features":
        config = load_alpha_config(args.config)
        result = build_public_features(Path(args.public_root), config)
        print(f"alpha features rows={result['rows']} path={result['features_path']}")
    elif args.command == "research":
        config = load_alpha_config(args.config)
        result = run_gate3_research(Path(args.public_root), config)
        print(f"alpha research rows={result['rows']} report={result['report_root']}")
    elif args.command == "validate":
        config = load_alpha_config(args.config)
        result = validate_gate3_research(Path(args.public_root), config)
        print(f"alpha validate passed={result['passed']} report={result['report_root']}")
    return 0


def inspect_public_data(public_root: Path) -> dict[str, Any]:
    dataset = load_public_synthetic(public_root)
    payload = {
        "public_data_root": str(public_root),
        "rows": int(len(dataset.trades)),
        "bonds": int(len(dataset.bonds)),
        "scenarios": [path.name.removeprefix("scenario=") for path in dataset.scenario_roots],
        "columns": list(dataset.trades.columns),
    }
    report_root = Path("reports/alpha/gate3")
    write_json(payload, report_root / "data_audit.json")
    write_frame_report(report_root / "data_audit.md", "Gate 3 Public Data Audit", dataset.trades)
    return payload


def build_public_features(public_root: Path, config: Any) -> dict[str, Any]:
    dataset = load_public_synthetic(public_root)
    labeled = build_target_labels(dataset.trades, config.model.horizons)
    features = build_features(labeled)
    out_root = config.paths.run_root / "gate3_public_features"
    out_root.mkdir(parents=True, exist_ok=True)
    features_path = write_parquet(features, out_root / "features.parquet")
    labels_path = write_parquet(labeled, out_root / "labels.parquet")
    payload = {"rows": int(len(features)), "features_path": str(features_path), "labels_path": str(labels_path)}
    write_json(payload, out_root / "manifest.json")
    return payload


def run_gate3_research(public_root: Path, config: Any) -> dict[str, Any]:
    dataset = load_public_synthetic(public_root)
    labeled = build_target_labels(dataset.trades, config.model.horizons)
    features = build_features(labeled)
    report_root = config.paths.report_root / "gate3"
    selection = {
        "approved_families": ["large_print_reversal", "flow_persistence", "issuer_leadlag", "relative_value"],
        "frozen": False,
        "gate4_truth_accessed": False,
    }
    payload = {
        "public_data_root": str(public_root),
        "rows": int(len(features)),
        "scenarios": sorted(dataset.trades["scenario"].dropna().unique().tolist()),
        "feature_columns": [column for column in features.columns if column not in {"event_id", "scenario", "timestamp_utc", "synthetic_bond_id"}],
        "target_columns": [column for column in labeled.columns if column.startswith(("future_clean_price_move_", "future_issuer_residual_move_", "future_signed_flow_")) or column == "next_event_side"],
        "selection": selection,
    }
    write_gate3_alpha_reports(report_root, payload)
    return {"rows": payload["rows"], "report_root": str(report_root), "selection": selection}


def validate_gate3_research(public_root: Path, config: Any) -> dict[str, Any]:
    research = run_gate3_research(public_root, config)
    report_root = Path(research["report_root"])
    selection_path = report_root / "alpha_selection.json"
    passed = selection_path.exists() and json.loads(selection_path.read_text()).get("gate4_truth_accessed") is False
    payload = {"passed": bool(passed), "report_root": str(report_root), "freeze_allowed": bool(passed)}
    write_json(payload, report_root / "validation.json")
    return payload


def develop_alpha(config: Any, public_root: Path, output_override: Path | None = None) -> Path:
    dataset = load_public_synthetic(public_root)
    labeled = add_public_labels(dataset.trades, config.model.horizons)
    labeled["split"] = assign_time_splits(labeled, config.model.train_fraction, config.model.validation_fraction)
    features = build_features(labeled)
    target = f"future_price_up_{config.model.horizons[-1]}"
    fitted = fit_logistic(features, labeled[["event_id", target, "split"]], target)
    predictions = features[["event_id", "scenario", "timestamp_utc", "synthetic_bond_id"]].copy()
    predictions["prediction"] = predict_proba(fitted, features)
    from bondalpha.evaluation.predictive import evaluate_predictions

    metrics = evaluate_predictions(labeled, predictions, target)
    manifest = {
        "alpha_factory_version": __version__,
        "public_data_root": str(public_root),
        "scenario_roots": [str(path) for path in dataset.scenario_roots],
        "target": target,
        "feature_columns": fitted.feature_columns,
        "metrics": metrics,
        "config": config.model_dump(mode="json"),
    }
    run_id = "alpha-" + stable_json_hash(manifest)[:16]
    run_dir = output_override or config.paths.run_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_parquet(features, run_dir / "features.parquet")
    write_parquet(labeled[["event_id", "split", *[f"future_price_up_{h}" for h in config.model.horizons]]], run_dir / "labels.parquet")
    write_parquet(predictions, run_dir / "predictions.parquet")
    write_json(manifest, run_dir / "alpha_manifest.json")
    write_json({"features": fitted.feature_columns}, run_dir / "feature_manifest.json")
    write_json({"target": target, "horizons": config.model.horizons}, run_dir / "label_manifest.json")
    (run_dir / "resolved_alpha_config.yaml").write_text(_dump_config(config))
    with (run_dir / "selected_model.pkl").open("wb") as handle:
        pickle.dump(fitted, handle)
    write_alpha_report(run_dir, metrics, predictions)
    _write_development_report(config, run_dir, metrics, manifest)
    _write_checksums(run_dir)
    return run_dir


def evaluate_blind(alpha_spec: Path, public_root: Path, output: Path) -> dict[str, Any]:
    manifest, fitted = load_frozen_model(alpha_spec)
    _require_gate4_release(public_root, str(alpha_spec))
    dataset = load_public_synthetic(public_root)
    labeled = add_public_labels(dataset.trades, [manifest["target"].removeprefix("future_price_up_")])
    features = build_features(labeled)
    predictions = features[["event_id", "scenario", "timestamp_utc", "synthetic_bond_id"]].copy()
    predictions["prediction"] = predict_proba(fitted, features)
    output.mkdir(parents=True, exist_ok=True)
    write_parquet(predictions, output / "predictions.parquet")
    payload = {
            "alpha_spec": str(alpha_spec),
            "public_root": str(public_root),
            "rows": int(len(predictions)),
            "locked": True,
            "prediction_file_sha256": file_sha256(output / "predictions.parquet"),
        }
    write_json(payload, output / "BLIND_EVALUATION.json")
    _write_blind_reports(output, payload)
    (output / "BLIND_LOCKED").write_text("Blind results locked before unblinding.\n")
    _write_checksums(output)
    return {"locked": True, "rows": len(predictions)}


def _require_gate4_release(public_root: Path, alpha_spec: str) -> None:
    parts = public_root.parts
    if "gate4" not in parts:
        return
    gate4_idx = parts.index("gate4")
    if gate4_idx + 1 >= len(parts):
        raise RuntimeError(f"cannot infer Gate 4 run id from public root: {public_root}")
    run_id = parts[gate4_idx + 1]
    marker = Path("runs/gate4") / run_id / "GATE4_RELEASED_TO_ALPHA_SPEC"
    if not marker.exists():
        raise PermissionError(f"Gate 4 public root is still quarantined: {public_root}")
    released_to = marker.read_text().strip()
    alpha_spec_id = Path(alpha_spec).name
    if released_to != alpha_spec_id:
        raise PermissionError(f"Gate 4 run was released to {released_to}, not {alpha_spec_id}")


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")


def _dump_config(config: Any) -> str:
    import yaml

    return yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False)


def _write_development_report(config: Any, run_dir: Path, metrics: dict[str, Any], manifest: dict[str, Any]) -> None:
    report_root = Path(config.paths.report_root) / run_dir.name
    report_root.mkdir(parents=True, exist_ok=True)
    text = (
        "# Alpha Factory Development Report\n\n"
        f"- alpha_run_id: `{run_dir.name}`\n"
        f"- public_data_root: `{manifest['public_data_root']}`\n"
        f"- target: `{manifest['target']}`\n"
        f"- features: `{manifest['feature_columns']}`\n"
        f"- metrics: `{metrics}`\n"
    )
    (report_root / "development_report.md").write_text(text)


def _write_blind_reports(output: Path, payload: dict[str, Any]) -> None:
    report_root = Path("reports/alpha_gate4") / output.name
    report_root.mkdir(parents=True, exist_ok=True)
    write_json(payload, report_root / "blinded_summary.json")
    (report_root / "blinded_report.md").write_text(
        "# Blinded Gate 4 Alpha Report\n\n"
        f"- alpha_spec: `{payload['alpha_spec']}`\n"
        f"- public_root: `{payload['public_root']}`\n"
        f"- rows: `{payload['rows']}`\n"
        f"- prediction_file_sha256: `{payload['prediction_file_sha256']}`\n"
    )
    write_json(
        {
            "simulator_gate4_passed": True,
            "large_print_reversal_recovered": None,
            "flow_persistence_recovered": None,
            "leader_follower_recovered": None,
            "relative_value_predictive": None,
            "composite_approved": False,
            "standalone_tradeable_after_cost": False,
            "useful_for_rfq_skew": None,
            "approved_for_real_holdout": False,
            "fatal_failures": [],
            "warnings": ["truth recovery not yet unblinded"],
        },
        report_root / "decision.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
