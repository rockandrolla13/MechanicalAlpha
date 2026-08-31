"""Freeze verified calibration runs into read-only model bundles."""

from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path
from typing import Any

from bondsim.calibration.frozen import verify_checksums
from bondsim.utils.hashing import file_sha256


def freeze_calibration(run_dir: Path, model_root: Path = Path("models"), allow_dirty: bool = True, force: bool = False) -> Path:
    """Copy a complete calibration run into `models/frozen/<calibration_id>`."""

    manifest = json.loads((run_dir / "calibration_manifest.json").read_text())
    checksum_failures = verify_checksums(run_dir)
    if checksum_failures:
        raise RuntimeError(f"cannot freeze run with checksum failures: {checksum_failures}")
    fatal_failed = [gate for gate in manifest.get("gates", []) if gate["severity"] == "fatal" and gate["status"] != "pass"]
    if fatal_failed:
        raise RuntimeError(f"cannot freeze run with fatal gate failures: {fatal_failed}")
    if manifest.get("git_dirty") and not allow_dirty:
        raise RuntimeError("cannot freeze dirty run without research override")
    calibration_id = manifest.get("calibration_id", "calibration-v1.0.0")
    frozen = model_root / "frozen" / calibration_id
    if frozen.exists():
        if not force:
            raise FileExistsError(f"frozen calibration already exists: {frozen}")
        _make_writable(frozen)
        shutil.rmtree(frozen)
    frozen.mkdir(parents=True)
    for name in [
        "resolved_config.yaml",
        "calibration_manifest.json",
        "seed_manifest.json",
        "source_fingerprint.json",
        "selected_models.json",
        "software_environment.json",
        "checksums.sha256",
    ]:
        shutil.copy2(run_dir / name, frozen / name)
    artifact_payloads = _artifact_payloads(run_dir, manifest)
    for dirname, payload in artifact_payloads.items():
        target = frozen / dirname
        target.mkdir()
        (target / "artifact.json").write_text(json.dumps(_strict_json_value(payload), indent=2, sort_keys=True, default=str, allow_nan=False) + "\n")
    (frozen / "FROZEN").write_text(calibration_id + "\n")
    checksums = []
    for path in sorted(p for p in frozen.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        checksums.append(f"{file_sha256(path)}  {path.relative_to(frozen)}")
    (frozen / "checksums.sha256").write_text("\n".join(checksums) + "\n")
    for path in frozen.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o444)
        elif path.is_dir():
            os.chmod(path, 0o555)
    return frozen


def _artifact_payloads(run_dir: Path, manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    source_run = str(run_dir)
    selected_model = _read_json(run_dir / "selected_models.json")
    source_fingerprint = _read_json(run_dir / "source_fingerprint.json")
    seed_manifest = _read_json(run_dir / "seed_manifest.json")
    gates = manifest.get("gates", [])
    hawkes = manifest.get("hawkes", {})
    liquidity = manifest.get("liquidity", [])
    synthcity = manifest.get("synthcity", {})
    common = {"source_run": source_run, "calibration_id": manifest.get("calibration_id"), "run_id": manifest.get("run_id")}
    return {
        "liquidity_model": {**common, "artifact_type": "manifest_backed_liquidity_model", "liquidity": liquidity},
        "activity_model": {**common, "artifact_type": "manifest_backed_activity_model", "seed_manifest": seed_manifest},
        "hawkes_model": {**common, "artifact_type": "manifest_backed_hawkes_model", "hawkes": hawkes},
        "mark_model": {**common, "artifact_type": "selected_mark_model", "selected_model": selected_model, "synthcity": synthcity},
        "fair_value_model": {**common, "artifact_type": "transaction_price_proxy_fair_value_model"},
        "ou_model": {**common, "artifact_type": "configured_ou_model"},
        "impact_model": {**common, "artifact_type": "configured_impact_model"},
        "leadlag_model": {**common, "artifact_type": "configured_leadlag_model"},
        "category_maps": {**common, "artifact_type": "source_schema_reference", "source_fingerprint": source_fingerprint},
        "train_derived_bins": {**common, "artifact_type": "frozen_plot_bins", "source": "Gate 2.5 calibration report plot_data"},
        "train_derived_thresholds": {**common, "artifact_type": "frozen_thresholds", "gates": gates},
        "validation_scores": {**common, "artifact_type": "validation_scores", "gates": gates},
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text()) if path.exists() else {}


def _strict_json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _strict_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_strict_json_value(item) for item in value]
    return value


def _make_writable(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            os.chmod(path, 0o644)
        elif path.is_dir():
            os.chmod(path, 0o755)
    os.chmod(root, 0o755)
