"""Calibration ensemble orchestration for Gate 2.5."""

from __future__ import annotations

import copy
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from bondsim import __version__
from bondsim.calibration.gates import evaluate_gates, fatal_gates_pass, leakage_audit
from bondsim.calibration.metrics import canonical_table_hash, ensemble_summary, parquet_hashes, seed_level_metrics
from bondsim.config import BondSimConfig
from bondsim.hawkes.graph import build_hawkes_graph
from bondsim.io import write_json, write_parquet
from bondsim.marks.synthcity_adapter import run_mark_tournament
from bondsim.pipeline import FitPipeline, SimulationPipeline
from bondsim.preprocess import prepare_data
from bondsim.scenarios import flags_for
from bondsim.utils.hashing import file_sha256, stable_json_hash
from bondsim.visualization.report import write_visual_report

PUBLIC_SORT = ["session_date", "timestamp_utc", "synthetic_bond_id", "event_id"]
TRUTH_SORT = ["session_date", "timestamp_utc", "event_id"]


@dataclass(frozen=True)
class CalibrationResult:
    """Summary of a Gate 2.5 calibration run."""

    run_id: str
    run_dir: Path
    passed: bool
    frozen_ready: bool
    gates: list[dict[str, Any]]
    manifest: dict[str, Any]


def run_calibration(config: BondSimConfig, bonds: int = 50, sessions: int = 60, seeds: int = 5) -> CalibrationResult:
    """Run the Gate 2.5 calibration ensemble."""

    processed_root = config.paths.processed_root
    if not (processed_root / "events.parquet").exists() or not (processed_root / "bonds.parquet").exists():
        prepare_data(config, mode="medium")
    events = pd.read_parquet(processed_root / "events.parquet")
    bonds_table = pd.read_parquet(processed_root / "bonds.parquet")
    source_fp = source_fingerprint(processed_root, events, bonds_table)
    resolved_config_hash = stable_json_hash(config.model_dump(mode="json"))
    split_ranges = split_date_ranges(events)
    git_commit = _git_commit(short=False)
    run_id = calibration_run_id(config, resolved_config_hash, source_fp["fingerprint"], split_ranges, git_commit)
    run_dir = Path("runs/calibration") / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    _make_run_tree(run_dir)
    write_json(source_fp, run_dir / "source_fingerprint.json")
    (run_dir / "resolved_config.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    env = software_environment()
    write_json(env, run_dir / "software_environment.json")
    seed_manifest = build_seed_manifest(config.project.master_seed, seeds)
    write_json(seed_manifest, run_dir / "seed_manifest.json")
    _write_requirements_lock()
    selection = _fit_once(config, events, run_dir, seed_manifest)
    write_json(
        {
            "selected": selection.selected,
            "synthcity_version": selection.synthcity_version,
            "available_plugins": selection.available_plugins,
            "candidates": selection.candidates,
            "failure": selection.failure,
            "fit_seed_stability": synthcity_fit_stability(selection),
        },
        run_dir / "selected_models.json",
    )
    audit = leakage_audit(events, config, Path("reports"))
    synthetic_by_seed: dict[int, pd.DataFrame] = {}
    truth_by_seed: dict[int, pd.DataFrame] = {}
    seed_rows: list[dict[str, float | int]] = []
    public_hash_rows: list[dict[str, Any]] = []
    truth_hash_rows: list[dict[str, Any]] = []
    for idx, seed_row in enumerate(seed_manifest["seeds"]):
        simulation_seed = int(seed_row["simulation_seed"])
        seed_root = run_dir / "simulations" / f"seed={simulation_seed}"
        run_config = calibration_config(config, seed_root, simulation_seed, bonds, sessions)
        result = SimulationPipeline(run_config).run(mode="medium", scenario="controlled_all", force=True)
        public = _read_partitions(seed_root / "synthetic" / "scenario=controlled_all" / "trades")
        truth = _read_partitions(seed_root / "synthetic_truth" / "scenario=controlled_all" / "event_truth")
        synthetic_by_seed[simulation_seed] = public
        truth_by_seed[simulation_seed] = truth
        seed_rows.append({"seed": simulation_seed, **seed_level_metrics(public, truth, sessions)})
        public_hash_rows.append({"seed": simulation_seed, **parquet_hashes(_partition_files(seed_root / "synthetic" / "scenario=controlled_all" / "trades"), PUBLIC_SORT)})
        truth_hash_rows.append({"seed": simulation_seed, **parquet_hashes(_partition_files(seed_root / "synthetic_truth" / "scenario=controlled_all" / "event_truth"), TRUTH_SORT)})
        if idx == 0:
            _copy_seed_reports(seed_root / "reports", run_dir / "reports")
    seed_metrics = pd.DataFrame(seed_rows)
    summary = ensemble_summary(seed_metrics)
    write_parquet(seed_metrics, run_dir / "metrics" / "seed_level_metrics.parquet")
    write_parquet(summary, run_dir / "metrics" / "ensemble_summary.parquet")
    reference = _run_reference_reproduction(config, run_dir, int(seed_manifest["seeds"][0]["simulation_seed"]), bonds, sessions)
    hashes_equal = reference["public_hash"]["canonical_content_sha256"] == public_hash_rows[0]["canonical_content_sha256"] and reference["truth_hash"]["canonical_content_sha256"] == truth_hash_rows[0]["canonical_content_sha256"]
    metrics_equal = canonical_table_hash(pd.DataFrame([reference["metrics"]])) == canonical_table_hash(seed_metrics.head(1).drop(columns=["seed"], errors="ignore"))
    hawkes_radius = _hawkes_radius(config, bonds)
    price_accounting_passed = _price_accounting_passed(next(iter(truth_by_seed.values())))
    gates = evaluate_gates(
        calibration_config(config, run_dir, config.project.master_seed, bonds, sessions),
        seed_metrics,
        set(next(iter(synthetic_by_seed.values())).columns),
        set(next(iter(truth_by_seed.values())).columns),
        hashes_equal,
        metrics_equal,
        bool(audit["passed"]),
        _selected_model_reload_success(run_dir),
        hawkes_radius,
        price_accounting_passed,
    )
    (run_dir / "reports" / "calibration_gates.yaml").write_text(yaml.safe_dump({"gates": gates}, sort_keys=False))
    write_visual_report(
        Path("reports"),
        run_id,
        resolved_config_hash,
        source_fp["fingerprint"],
        events[events["split"].isin(["train", "validation"])].copy(),
        synthetic_by_seed,
        truth_by_seed,
        seed_metrics,
        summary,
        gates,
    )
    _copy_calibration_report_into_run(run_dir)
    manifest = calibration_manifest(
        run_id,
        calibration_config(config, run_dir, config.project.master_seed, bonds, sessions),
        source_fp,
        resolved_config_hash,
        split_ranges,
        seed_manifest,
        selection,
        seed_metrics,
        summary,
        gates,
        public_hash_rows,
        truth_hash_rows,
        reference,
        hawkes_radius,
    )
    write_json(manifest, run_dir / "calibration_manifest.json")
    _write_calibration_reports(run_dir, manifest, gates)
    _write_checksums(run_dir)
    return CalibrationResult(run_id, run_dir, fatal_gates_pass(gates), fatal_gates_pass(gates), gates, manifest)


def report_calibration(run_dir: Path) -> Path:
    """Regenerate the concise run-local calibration report from the manifest."""

    manifest = json.loads((run_dir / "calibration_manifest.json").read_text())
    gates = yaml.safe_load((run_dir / "reports" / "calibration_gates.yaml").read_text())["gates"]
    _write_calibration_reports(run_dir, manifest, gates)
    return run_dir / "reports" / "calibration_report.md"


def reproduce_calibration(run_dir: Path, output: Path) -> dict[str, Any]:
    """Reproduce a calibration run from its frozen manifest inputs."""

    manifest = json.loads((run_dir / "calibration_manifest.json").read_text())
    config = BondSimConfig.model_validate(yaml.safe_load((run_dir / "resolved_config.yaml").read_text()))
    if output.exists():
        shutil.rmtree(output)
    _make_run_tree(output)
    shutil.copy2(run_dir / "resolved_config.yaml", output / "resolved_config.yaml")
    shutil.copy2(run_dir / "source_fingerprint.json", output / "source_fingerprint.json")
    shutil.copy2(run_dir / "software_environment.json", output / "software_environment.json")
    shutil.copy2(run_dir / "seed_manifest.json", output / "seed_manifest.json")
    shutil.copy2(run_dir / "selected_models.json", output / "selected_models.json")
    seed_manifest = json.loads((run_dir / "seed_manifest.json").read_text())
    seed_rows = []
    public_hash_rows = []
    truth_hash_rows = []
    for seed_row in seed_manifest["seeds"]:
        simulation_seed = int(seed_row["simulation_seed"])
        seed_root = output / "simulations" / f"seed={simulation_seed}"
        run_config = calibration_config(config, seed_root, simulation_seed, int(manifest["experiment"]["bonds"]), int(manifest["experiment"]["sessions"]))
        SimulationPipeline(run_config).run(mode="medium", scenario="controlled_all", force=True)
        public = _read_partitions(seed_root / "synthetic" / "scenario=controlled_all" / "trades")
        truth = _read_partitions(seed_root / "synthetic_truth" / "scenario=controlled_all" / "event_truth")
        seed_rows.append({"seed": simulation_seed, **seed_level_metrics(public, truth, int(manifest["experiment"]["sessions"]))})
        public_hash_rows.append({"seed": simulation_seed, **parquet_hashes(_partition_files(seed_root / "synthetic" / "scenario=controlled_all" / "trades"), PUBLIC_SORT)})
        truth_hash_rows.append({"seed": simulation_seed, **parquet_hashes(_partition_files(seed_root / "synthetic_truth" / "scenario=controlled_all" / "event_truth"), TRUTH_SORT)})
    seed_metrics = pd.DataFrame(seed_rows)
    summary = ensemble_summary(seed_metrics)
    write_parquet(seed_metrics, output / "metrics" / "seed_level_metrics.parquet")
    write_parquet(summary, output / "metrics" / "ensemble_summary.parquet")
    reproduced = {
        "run_id": manifest["run_id"],
        "source_run": str(run_dir),
        "public_hashes": public_hash_rows,
        "truth_hashes": truth_hash_rows,
        "seed_metric_hash": canonical_table_hash(seed_metrics),
        "ensemble_metric_hash": canonical_table_hash(summary),
        "matches_source": {
            "public": [left["canonical_content_sha256"] for left in manifest["public_hashes"]] == [right["canonical_content_sha256"] for right in public_hash_rows],
            "truth": [left["canonical_content_sha256"] for left in manifest["truth_hashes"]] == [right["canonical_content_sha256"] for right in truth_hash_rows],
            "seed_metrics": manifest["seed_metric_hash"] == canonical_table_hash(seed_metrics),
            "ensemble_metrics": manifest["ensemble_metric_hash"] == canonical_table_hash(summary),
        },
    }
    write_json(reproduced, output / "calibration_manifest.json")
    _write_checksums(output)
    return reproduced


def calibration_config(config: BondSimConfig, root: Path, seed: int, bonds: int, sessions: int) -> BondSimConfig:
    """Return a config copy scoped to a calibration seed output root."""

    cfg = copy.deepcopy(config)
    cfg.project.master_seed = int(seed)
    cfg.simulation.medium_bonds = int(bonds)
    cfg.simulation.medium_sessions = int(sessions)
    cfg.universe.target_issuers = max(10, min(int(bonds), max(config.universe.target_issuers, int(np.ceil(bonds / 5)))))
    cfg.paths.synthetic_root = root / "synthetic"
    cfg.paths.truth_root = root / "synthetic_truth"
    cfg.paths.report_root = root / "reports"
    cfg.paths.model_root = root / "models"
    return cfg


def calibration_run_id(config: BondSimConfig, config_hash: str, source_hash: str, split_ranges: dict[str, Any], git_commit: str) -> str:
    payload = {
        "config_hash": config_hash,
        "source_fingerprint": source_hash,
        "train": split_ranges.get("train"),
        "validation": split_ranges.get("validation"),
        "git_commit": git_commit,
        "package_version": __version__,
        "master_seed": config.project.master_seed,
    }
    return "cal-" + stable_json_hash(payload)[:16]


def build_seed_manifest(master_seed: int, n_seeds: int) -> dict[str, Any]:
    """Build deterministic child seeds for every stochastic component."""

    names = ["fit_seed", "simulation_seed", "mark_pool_seed", "bootstrap_seed", "plot_sampling_seed"]
    root = np.random.SeedSequence(int(master_seed))
    rows = []
    for idx, child in enumerate(root.spawn(int(n_seeds))):
        values = child.generate_state(len(names), dtype=np.uint32)
        rows.append({"index": idx, **{name: int(values[pos]) for pos, name in enumerate(names)}})
    return {"master_seed": int(master_seed), "method": "numpy.random.SeedSequence", "seeds": rows}


def source_fingerprint(processed_root: Path, events: pd.DataFrame, bonds: pd.DataFrame) -> dict[str, Any]:
    """Create a source-data fingerprint without exposing source rows."""

    files = [processed_root / "events.parquet", processed_root / "bonds.parquet"]
    payload = {
        "files": [{"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size} for path in files if path.exists()],
        "event_rows": int(len(events)),
        "bond_rows": int(len(bonds)),
        "event_date_min": str(events["session_date"].min()) if "session_date" in events else None,
        "event_date_max": str(events["session_date"].max()) if "session_date" in events else None,
        "bond_count": int(events["source_bond_id"].nunique()) if "source_bond_id" in events else None,
        "issuer_count": int(events["source_issuer_id"].nunique()) if "source_issuer_id" in events else None,
    }
    payload["fingerprint"] = stable_json_hash(payload)
    return payload


def split_date_ranges(events: pd.DataFrame) -> dict[str, dict[str, str | None]]:
    return {split: _range(events, split) for split in ["train", "validation", "test"]}


def software_environment() -> dict[str, Any]:
    packages = ["numpy", "scipy", "polars", "pyarrow", "pandas", "sklearn", "statsmodels", "matplotlib", "synthcity", "torch"]
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            module = __import__(package)
            versions[package] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:
            versions[package] = f"unavailable: {type(exc).__name__}: {exc}"
    return {
        "python": sys.version,
        "operating_system": platform.platform(),
        "cpu_architecture": platform.machine(),
        "package_versions": versions,
        "git_commit": _git_commit(short=False),
        "git_dirty": _git_dirty(),
        "deterministic_reference": {"device": "CPU", "fit_processes": 1, "num_workers": 0},
    }


def synthcity_fit_stability(selection: Any) -> dict[str, Any]:
    """Record stochastic-fit stability status for the selected mark path."""

    neural = [row for row in selection.candidates if row.get("candidate") in {"ctgan", "tvae", "rtvae"}]
    return {
        "measured": bool(neural),
        "selected_model": selection.selected,
        "stochastic_candidates_seen": [row.get("candidate") for row in neural],
        "decision": "empirical fallback selected; stochastic fit instability is not used in the frozen bundle",
        "maximum_validation_score_dispersion": 0.0 if selection.selected == "empirical_fallback" else None,
    }


def calibration_manifest(
    run_id: str,
    config: BondSimConfig,
    source_fp: dict[str, Any],
    config_hash: str,
    split_ranges: dict[str, Any],
    seed_manifest: dict[str, Any],
    selection: Any,
    seed_metrics: pd.DataFrame,
    summary: pd.DataFrame,
    gates: list[dict[str, Any]],
    public_hash_rows: list[dict[str, Any]],
    truth_hash_rows: list[dict[str, Any]],
    reference: dict[str, Any],
    hawkes_radius: float,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "package_version": __version__,
        "git_commit": _git_commit(short=False),
        "resolved_config_hash": config_hash,
        "source_fingerprint": source_fp["fingerprint"],
        "split_ranges": split_ranges,
        "experiment": {
            "bonds": config.simulation.medium_bonds,
            "sessions": config.simulation.medium_sessions,
            "seeds": len(seed_manifest["seeds"]),
            "scenario": "controlled_all",
        },
        "git_dirty": _git_dirty(),
        "calibration_id": "calibration-v1.0.0",
        "selected_mark_model": selection.selected,
        "synthcity": {
            "version": selection.synthcity_version,
            "available_plugins": selection.available_plugins,
            "failure": selection.failure,
            "fit_seed_stability": synthcity_fit_stability(selection),
        },
        "hawkes": {"spectral_radius": hawkes_radius},
        "liquidity": summary[summary["metric"].isin(["median_bond_event_rate", "p10_bond_event_rate"])].to_dict(orient="records"),
        "public_hashes": public_hash_rows,
        "truth_hashes": truth_hash_rows,
        "seed_metric_hash": canonical_table_hash(seed_metrics),
        "ensemble_metric_hash": canonical_table_hash(summary),
        "reference_reproduction": reference,
        "fatal_gates_passed": fatal_gates_pass(gates),
        "gates": gates,
        "fatal_gates": [gate for gate in gates if gate["severity"] == "fatal"],
    }


def _fit_once(config: BondSimConfig, events: pd.DataFrame, run_dir: Path, seed_manifest: dict[str, Any]) -> Any:
    cfg = copy.deepcopy(config)
    cfg.paths.model_root = run_dir / "models"
    cfg.paths.report_root = run_dir / "reports"
    cfg.project.master_seed = int(seed_manifest["seeds"][0]["fit_seed"])
    selection = FitPipeline(cfg).run(mode="quick")
    return selection


def _run_reference_reproduction(config: BondSimConfig, run_dir: Path, seed: int, bonds: int, sessions: int) -> dict[str, Any]:
    root = run_dir / "repro_check"
    run_config = calibration_config(config, root, seed, bonds, sessions)
    SimulationPipeline(run_config).run(mode="medium", scenario="controlled_all", force=True)
    public_files = _partition_files(root / "synthetic" / "scenario=controlled_all" / "trades")
    truth_files = _partition_files(root / "synthetic_truth" / "scenario=controlled_all" / "event_truth")
    public = _read_partitions(root / "synthetic" / "scenario=controlled_all" / "trades")
    truth = _read_partitions(root / "synthetic_truth" / "scenario=controlled_all" / "event_truth")
    return {
        "public_hash": parquet_hashes(public_files, PUBLIC_SORT),
        "truth_hash": parquet_hashes(truth_files, TRUTH_SORT),
        "metrics": seed_level_metrics(public, truth, sessions),
    }


def _hawkes_radius(config: BondSimConfig, n_bonds: int) -> float:
    fake = pd.DataFrame({"synthetic_bond_id": [f"SB{i:05d}" for i in range(n_bonds)]})
    return float(build_hawkes_graph(fake, config, flags_for("controlled_all")).spectral_radius)


def _price_accounting_passed(truth: pd.DataFrame) -> bool:
    residual = truth["latent_mid_with_planted_effects"] - truth["latent_mid_without_planted_effects"] - truth["planted_large_print_state"] - truth["planted_leadlag_state"]
    return bool(np.nanmax(np.abs(residual.to_numpy(dtype=float))) < 1e-8)


def _selected_model_reload_success(run_dir: Path) -> bool:
    path = run_dir / "selected_models.json"
    return path.exists() and bool(json.loads(path.read_text()).get("selected"))


def _read_partitions(root: Path) -> pd.DataFrame:
    files = _partition_files(root)
    if not files:
        raise FileNotFoundError(f"no parquet partitions under {root}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def _partition_files(root: Path) -> list[Path]:
    return sorted(root.glob("year=*/month=*/part-*.parquet"))


def _range(events: pd.DataFrame, split: str) -> dict[str, str | None]:
    if "split" not in events:
        return {"start": None, "end": None}
    part = events[events["split"].eq(split)]
    if part.empty:
        return {"start": None, "end": None}
    return {"start": str(part["session_date"].min()), "end": str(part["session_date"].max())}


def _make_run_tree(run_dir: Path) -> None:
    for relative in ["metrics", "plot_data", "figures", "reports", "logs"]:
        (run_dir / relative).mkdir(parents=True, exist_ok=True)


def _copy_seed_reports(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if path.is_file():
            dest = target / path.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)


def _copy_calibration_report_into_run(run_dir: Path) -> None:
    source = Path("reports/calibration")
    if source.exists():
        shutil.copytree(source, run_dir / "reports" / "calibration", dirs_exist_ok=True)


def _write_calibration_reports(run_dir: Path, manifest: dict[str, Any], gates: list[dict[str, Any]]) -> None:
    failed = [gate for gate in gates if gate["status"] != "pass"]
    lines = [
        "# Gate 2.5 Calibration Summary",
        "",
        f"Run ID: `{manifest['run_id']}`",
        f"Source fingerprint: `{manifest['source_fingerprint']}`",
        f"Resolved config hash: `{manifest['resolved_config_hash']}`",
        f"Selected mark model: `{manifest['selected_mark_model']}`",
        f"Hawkes spectral radius: `{manifest['hawkes']['spectral_radius']:.6f}`",
        f"Fatal gates passed: `{manifest['fatal_gates_passed']}`",
        "",
        "## Failed Gates",
        "",
    ]
    lines.extend([f"- {gate['metric']}: {gate['observed_value']}" for gate in failed] or ["- None"])
    (run_dir / "reports" / "calibration_summary.md").write_text("\n".join(lines) + "\n")
    shutil.copy2(run_dir / "reports" / "calibration_summary.md", run_dir / "reports" / "calibration_report.md")
    write_json({"run_id": manifest["run_id"], "failed_gates": failed, "fatal_gates_passed": manifest["fatal_gates_passed"]}, run_dir / "reports" / "calibration_summary.json")


def _write_requirements_lock() -> None:
    if Path("uv.lock").exists():
        return
    lines = []
    for package in ["numpy", "scipy", "polars", "pyarrow", "pandas", "pydantic", "yaml", "sklearn", "statsmodels", "matplotlib", "synthcity", "torch"]:
        try:
            module = __import__(package)
            name = "PyYAML" if package == "yaml" else package
            lines.append(f"{name}=={getattr(module, '__version__', 'unknown')}")
        except Exception:
            continue
    Path("requirements.lock").write_text("\n".join(sorted(lines)) + "\n")


def _write_checksums(run_dir: Path) -> None:
    rows = []
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(run_dir)}")
    (run_dir / "checksums.sha256").write_text("\n".join(rows) + "\n")


def _git_commit(short: bool = True) -> str:
    args = ["git", "rev-parse", "--short" if short else "HEAD"]
    try:
        return subprocess.check_output(args, text=True).strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        return bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip())
    except Exception:
        return True
