"""Gate 4 readiness audit without simulation or refitting."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bondsim.calibration.frozen import current_software_environment, load_frozen_calibration
from bondsim.config import BondSimConfig
from bondsim.io import write_json
from bondsim.outputs import FORBIDDEN_PUBLIC_COLUMNS
from bondsim.utils.hashing import file_sha256


def run_gate4_readiness_audit(config: BondSimConfig) -> dict[str, Any]:
    """Write Gate 4 readiness reports and return the readiness payload."""

    report_root = config.paths.report_root / "gate4"
    report_root.mkdir(parents=True, exist_ok=True)
    blocking: list[str] = []
    warnings: list[str] = []
    gate3_path = config.paths.report_root / "gate3" / "GATE3_DECISION.json"
    gate3_decision = _read_json_if_exists(gate3_path)
    if not gate3_decision:
        blocking.append(f"missing Gate 3 decision: {gate3_path}")
    approved = bool(gate3_decision.get("approved_for_gate4"))
    if gate3_decision and not approved:
        blocking.append("Gate 3 decision does not approve Gate 4")
    if gate3_decision.get("fatal_failures"):
        blocking.append(f"Gate 3 fatal failures remain: {gate3_decision['fatal_failures']}")
    calibration_id = config.frozen_calibration_id or gate3_decision.get("calibration_id")
    frozen = None
    frozen_found = False
    checksums_valid = False
    if calibration_id:
        try:
            frozen = load_frozen_calibration(str(calibration_id), config.paths.model_root)
            frozen_found = True
            checksums_valid = not frozen.checksum_failures
            warnings.extend(frozen.environment_deviations)
            warnings.extend(_immutability_warnings(frozen.path))
        except Exception as exc:
            blocking.append(f"frozen calibration failed to load: {type(exc).__name__}: {exc}")
    else:
        blocking.append("no calibration_id found in Gate 3 decision or config")
    if not os.environ.get("BONDSIM_DATA_ROOT"):
        warnings.append("BONDSIM_DATA_ROOT is not set in this shell")
    if not Path("SYNTHETIC_SIMULATOR_MASTER_PROMPT.md").exists():
        warnings.append("SYNTHETIC_SIMULATOR_MASTER_PROMPT.md is not present at repository root")
    public_roots = sorted(Path("data/medium").glob("seed=*/synthetic/scenario=*"))
    truth_roots = sorted(Path("data/medium").glob("seed=*/synthetic_truth/scenario=*"))
    public_available = bool(public_roots)
    if not public_available:
        blocking.append("Gate 3 public synthetic data not found under data/medium")
    if not truth_roots:
        blocking.append("Gate 3 truth synthetic data not found under data/medium")
    schema_audit = audit_public_truth_separation(public_roots, truth_roots)
    if not schema_audit["public_truth_separation_valid"]:
        blocking.extend(schema_audit["failures"])
    gate4_state = audit_gate4_output_state(Path("data/synthetic/gate4"), Path("runs/gate4"))
    warnings.extend(gate4_state["warnings"])
    if gate4_state["blocking_failures"]:
        blocking.extend(gate4_state["blocking_failures"])
    inventory = build_artifact_inventory(
        gate3_path=gate3_path,
        frozen_path=frozen.path if frozen else config.paths.model_root / "frozen" / str(calibration_id),
        public_roots=public_roots,
        truth_roots=truth_roots,
    )
    resolved_path = Path("configs/gate4.resolved.yaml")
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    readiness = {
        "gate3_decision_found": gate3_path.exists(),
        "approved_for_gate4": approved,
        "frozen_calibration_found": frozen_found,
        "checksums_valid": checksums_valid,
        "public_truth_separation_valid": schema_audit["public_truth_separation_valid"],
        "gate3_public_data_available": public_available,
        "gate4_ready": not blocking,
        "blocking_failures": blocking,
        "warnings": warnings,
        "calibration_id": calibration_id,
        "source_fingerprint": frozen.source_fingerprint_hash if frozen else None,
        "resolved_config_hash": frozen.resolved_config_hash if frozen else None,
        "git": git_state(),
        "software_environment": current_software_environment(),
        "gate4_output_state": gate4_state,
    }
    write_json(readiness, report_root / "readiness_audit.json")
    write_json(inventory, report_root / "artifact_inventory.json")
    write_json(schema_audit, report_root / "schema_separation_audit.json")
    (report_root / "readiness_audit.md").write_text(_readiness_markdown(readiness))
    return readiness


def audit_public_truth_separation(public_roots: list[Path], truth_roots: list[Path]) -> dict[str, Any]:
    """Verify public Gate 3 parquet samples do not contain truth columns."""

    failures: list[str] = []
    public_files = _sample_partitions(public_roots, "trades")
    truth_files = _sample_partitions(truth_roots, "event_truth")
    public_columns: dict[str, list[str]] = {}
    truth_columns: dict[str, list[str]] = {}
    for path in public_files:
        columns = list(pd.read_parquet(path, columns=None).columns)
        public_columns[str(path)] = columns
        leaked = sorted(FORBIDDEN_PUBLIC_COLUMNS.intersection(columns))
        token_leaks = [column for column in columns if _truth_like(column)]
        if leaked or token_leaks:
            failures.append(f"public file has forbidden columns {leaked + token_leaks}: {path}")
    for path in truth_files:
        truth_columns[str(path)] = list(pd.read_parquet(path, columns=None).columns)
    overlap = set(public_files).intersection(truth_files)
    if overlap:
        failures.append(f"public and truth partitions overlap: {sorted(map(str, overlap))}")
    return {
        "public_truth_separation_valid": not failures,
        "public_files_checked": [str(path) for path in public_files],
        "truth_files_checked": [str(path) for path in truth_files],
        "public_columns": public_columns,
        "truth_columns": truth_columns,
        "failures": failures,
    }


def audit_gate4_output_state(public_root: Path, run_root: Path) -> dict[str, Any]:
    """Report existing Gate 4 directories and detect incomplete untracked runs."""

    warnings: list[str] = []
    blocking: list[str] = []
    public_runs = sorted(path for path in public_root.glob("gate4-*") if path.is_dir())
    run_dirs = sorted(path for path in run_root.glob("gate4-*") if path.is_dir())
    for path in run_dirs:
        manifest = path / "gate4_manifest.json"
        if not manifest.exists():
            blocking.append(f"Gate 4 run directory lacks manifest: {path}")
    for path in public_runs:
        manifests = sorted(path.glob("scenario=*/manifest.json"))
        if path.name not in {run.name for run in run_dirs}:
            warnings.append(f"Gate 4 public output has no matching run directory: {path}")
        if manifests and len(manifests) < 6:
            warnings.append(f"Gate 4 public output appears partial: {path} has {len(manifests)} scenario manifests")
    return {
        "public_runs": [str(path) for path in public_runs],
        "run_dirs": [str(path) for path in run_dirs],
        "blocking_failures": blocking,
        "warnings": warnings,
    }


def build_artifact_inventory(gate3_path: Path, frozen_path: Path, public_roots: list[Path], truth_roots: list[Path]) -> dict[str, Any]:
    """Collect file-level inventory for the readiness audit."""

    selected = [gate3_path]
    selected.extend(sorted(frozen_path.glob("*")) if frozen_path.exists() else [])
    selected.extend(path / "manifest.json" for path in public_roots if (path / "manifest.json").exists())
    selected.extend(path / "manifest.json" for path in truth_roots if (path / "manifest.json").exists())
    files = []
    for path in selected:
        files.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() and path.is_file() else None,
                "sha256": file_sha256(path) if path.exists() and path.is_file() else None,
            }
        )
    return {"files": files, "counts": {"gate3_public_roots": len(public_roots), "gate3_truth_roots": len(truth_roots)}}


def git_state() -> dict[str, Any]:
    return {
        "branch": _git(["git", "branch", "--show-current"]),
        "commit": _git(["git", "rev-parse", "HEAD"]),
        "dirty_files": _git(["git", "status", "--short"]).splitlines(),
    }


def _immutability_warnings(path: Path) -> list[str]:
    if not (path / "FROZEN").exists():
        return [f"frozen bundle marker missing: {path / 'FROZEN'}"]
    writable = [item for item in path.rglob("*") if item.is_file() and os.access(item, os.W_OK)]
    if writable:
        return [f"frozen calibration files are writable on this filesystem: {len(writable)} files"]
    return []


def _sample_partitions(roots: list[Path], dataset: str) -> list[Path]:
    files: list[Path] = []
    for root in roots[:6]:
        files.extend(sorted((root / dataset).glob("year=*/month=*/part-*.parquet"))[:1])
    return files


def _truth_like(column: str) -> bool:
    lower = column.lower()
    return any(token in lower for token in ["truth", "latent_", "planted_", "hawkes_parent", "hawkes_cluster"])


def _read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _git(command: list[str]) -> str:
    try:
        return subprocess.check_output(command, text=True).strip()
    except Exception:
        return "unknown"


def _readiness_markdown(readiness: dict[str, Any]) -> str:
    failures = "\n".join(f"- {item}" for item in readiness["blocking_failures"]) or "- none"
    warnings = "\n".join(f"- {item}" for item in readiness["warnings"]) or "- none"
    return (
        "# Gate 4 Readiness Audit\n\n"
        f"- gate4_ready: `{readiness['gate4_ready']}`\n"
        f"- approved_for_gate4: `{readiness['approved_for_gate4']}`\n"
        f"- frozen_calibration_found: `{readiness['frozen_calibration_found']}`\n"
        f"- checksums_valid: `{readiness['checksums_valid']}`\n"
        f"- public_truth_separation_valid: `{readiness['public_truth_separation_valid']}`\n"
        f"- gate3_public_data_available: `{readiness['gate3_public_data_available']}`\n\n"
        "## Blocking Failures\n\n"
        f"{failures}\n\n"
        "## Warnings\n\n"
        f"{warnings}\n"
    )
