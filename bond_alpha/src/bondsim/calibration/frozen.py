"""Frozen calibration bundle loading and verification."""

from __future__ import annotations

import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from bondsim.utils.hashing import file_sha256


@dataclass(frozen=True)
class FrozenCalibrationBundle:
    """Verified immutable calibration bundle used by Gate 3."""

    calibration_id: str
    path: Path
    manifest: dict[str, Any]
    source_fingerprint: dict[str, Any]
    resolved_config: dict[str, Any]
    selected_models: dict[str, Any]
    software_environment: dict[str, Any]
    checksum_failures: list[str]
    environment_deviations: list[str]

    @property
    def source_fingerprint_hash(self) -> str:
        return str(self.source_fingerprint.get("fingerprint", ""))

    @property
    def resolved_config_hash(self) -> str:
        return str(self.manifest.get("resolved_config_hash", ""))


def load_frozen_calibration(
    calibration_id: str,
    model_root: Path = Path("models"),
    *,
    expected_source_fingerprint: str | None = None,
    expected_config_hash: str | None = None,
) -> FrozenCalibrationBundle:
    """Load and verify a frozen calibration bundle."""

    path = model_root / "frozen" / calibration_id
    if not path.exists():
        raise FileNotFoundError(f"frozen calibration bundle not found: {path}")
    marker = (path / "FROZEN").read_text().strip()
    if marker != calibration_id:
        raise RuntimeError(f"frozen marker mismatch: expected {calibration_id}, found {marker}")
    checksum_failures = verify_checksums(path)
    if checksum_failures:
        raise RuntimeError(f"frozen calibration checksum failures: {checksum_failures}")
    manifest = _json(path / "calibration_manifest.json")
    source_fingerprint = _json(path / "source_fingerprint.json")
    selected_models = _json(path / "selected_models.json")
    software_environment = _json(path / "software_environment.json")
    resolved_config = yaml.safe_load((path / "resolved_config.yaml").read_text()) or {}
    if expected_source_fingerprint and source_fingerprint.get("fingerprint") != expected_source_fingerprint:
        raise RuntimeError(
            "source fingerprint mismatch: "
            f"expected {expected_source_fingerprint}, found {source_fingerprint.get('fingerprint')}"
        )
    if expected_config_hash and manifest.get("resolved_config_hash") != expected_config_hash:
        raise RuntimeError(
            "resolved config hash mismatch: "
            f"expected {expected_config_hash}, found {manifest.get('resolved_config_hash')}"
        )
    return FrozenCalibrationBundle(
        calibration_id=calibration_id,
        path=path,
        manifest=manifest,
        source_fingerprint=source_fingerprint,
        resolved_config=resolved_config,
        selected_models=selected_models,
        software_environment=software_environment,
        checksum_failures=checksum_failures,
        environment_deviations=software_environment_deviations(software_environment),
    )


def verify_checksums(root: Path) -> list[str]:
    """Verify `checksums.sha256` entries under a run or frozen bundle."""

    checksum_path = root / "checksums.sha256"
    if not checksum_path.exists():
        return [f"missing {checksum_path}"]
    failures: list[str] = []
    for line in checksum_path.read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split(maxsplit=1)
        if relative == "checksums.sha256":
            continue
        path = root / relative
        if not path.exists():
            failures.append(f"missing {relative}")
        else:
            observed = file_sha256(path)
            if observed != expected:
                failures.append(f"{relative}: expected {expected}, observed {observed}")
    return failures


def software_environment_deviations(frozen_environment: dict[str, Any]) -> list[str]:
    """Return package/version deviations from the frozen environment."""

    current = current_software_environment()
    deviations = []
    frozen_packages = frozen_environment.get("package_versions", {})
    current_packages = current.get("package_versions", {})
    for name, frozen_version in sorted(frozen_packages.items()):
        observed = current_packages.get(name)
        if observed != frozen_version:
            deviations.append(f"{name}: frozen={frozen_version}, current={observed}")
    for key in ["python", "operating_system", "cpu_architecture"]:
        if current.get(key) != frozen_environment.get(key):
            deviations.append(f"{key}: frozen={frozen_environment.get(key)}, current={current.get(key)}")
    return deviations


def current_software_environment() -> dict[str, Any]:
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
        "git_commit": _git_commit(),
    }


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"
