"""Compare calibration and reproduction run directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def compare_runs(left: Path, right: Path, report_root: Path = Path("reports/calibration")) -> dict[str, Any]:
    """Compare deterministic calibration artifacts."""

    report_root.mkdir(parents=True, exist_ok=True)
    left_manifest = _json(left, "calibration_manifest.json")
    right_manifest = _json(right, "calibration_manifest.json")
    if "matches_source" in right_manifest:
        canonical_hashes_equal = all(bool(value) for value in right_manifest["matches_source"].values())
        manifest_equal = right_manifest.get("run_id") == left_manifest.get("run_id")
    else:
        canonical_hashes_equal = _canonical_hash_record(left_manifest) == _canonical_hash_record(right_manifest)
        manifest_equal = _strip_paths(left_manifest) == _strip_paths(right_manifest)
    result = {
        "left": str(left),
        "right": str(right),
        "configuration_equal": _load(left, "resolved_config.yaml") == _load(right, "resolved_config.yaml"),
        "source_fingerprint_equal": _json(left, "source_fingerprint.json") == _json(right, "source_fingerprint.json"),
        "software_environment_equal": _json(left, "software_environment.json") == _json(right, "software_environment.json"),
        "selected_models_equal": _json(left, "selected_models.json") == _json(right, "selected_models.json"),
        "manifest_run_id_equal": manifest_equal,
        "canonical_content_hashes_equal": canonical_hashes_equal,
    }
    result["passed"] = all(value for key, value in result.items() if key.endswith("_equal"))
    name = f"comparison_{left.name}_{right.name}"
    result["report_json"] = str(report_root / f"{name}.json")
    result["report_markdown"] = str(report_root / f"{name}.md")
    (report_root / f"{name}.json").write_text(json.dumps(result, indent=2, sort_keys=True))
    (report_root / f"{name}.md").write_text("# Calibration Comparison\n\n```json\n" + json.dumps(result, indent=2, sort_keys=True) + "\n```\n")
    return result


def _load(root: Path, name: str) -> str:
    path = root / name
    return path.read_text() if path.exists() else ""


def _json(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    return json.loads(path.read_text()) if path.exists() else {}


def _strip_paths(value: dict[str, Any]) -> dict[str, Any]:
    copy = dict(value)
    copy.pop("run_dir", None)
    copy.pop("created_logs", None)
    return copy


def _canonical_hash_record(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "public": [row.get("canonical_content_sha256") for row in value.get("public_hashes", [])],
        "truth": [row.get("canonical_content_sha256") for row in value.get("truth_hashes", [])],
        "seed_metric_hash": value.get("seed_metric_hash"),
        "ensemble_metric_hash": value.get("ensemble_metric_hash"),
    }
