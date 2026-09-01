"""Alpha specification freeze and checksum utilities."""

from __future__ import annotations

import json
import pickle
import shutil
from pathlib import Path
from typing import Any

import yaml

from bondsim.io import write_json
from bondsim.utils.hashing import file_sha256, stable_json_hash


def freeze_alpha_spec(run_dir: Path, frozen_root: Path = Path("models/alpha_frozen"), *, force: bool = False) -> Path:
    manifest = json.loads((run_dir / "alpha_manifest.json").read_text())
    alpha_spec_id = "alpha-spec-" + stable_json_hash(manifest)[:12]
    target = frozen_root / alpha_spec_id
    if target.exists() and not force:
        raise FileExistsError(f"alpha spec already frozen: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name in ["alpha_manifest.json", "selected_model.pkl", "feature_manifest.json", "label_manifest.json"]:
        source = run_dir / name
        if source.exists():
            shutil.copy2(source, target / name)
    _write_spec_files(run_dir, target, manifest)
    write_json({"alpha_spec_id": alpha_spec_id, "source_run": str(run_dir), "manifest_hash": stable_json_hash(manifest)}, target / "frozen_spec.json")
    (target / "FROZEN").write_text(alpha_spec_id + "\n")
    (target / "ALPHA_FROZEN").write_text(alpha_spec_id + "\n")
    _write_checksums(target)
    return target


def load_frozen_model(spec_root: Path) -> tuple[dict[str, Any], Any]:
    marker = (spec_root / "FROZEN").read_text().strip()
    metadata = json.loads((spec_root / "frozen_spec.json").read_text())
    if metadata["alpha_spec_id"] != marker:
        raise RuntimeError("alpha spec frozen marker mismatch")
    failures = verify_checksums(spec_root)
    if failures:
        raise RuntimeError(f"alpha spec checksum failures: {failures}")
    manifest = json.loads((spec_root / "alpha_manifest.json").read_text())
    with (spec_root / "selected_model.pkl").open("rb") as handle:
        model = pickle.load(handle)
    return manifest, model


def verify_checksums(root: Path) -> list[str]:
    failures = []
    for line in (root / "checksums.sha256").read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        if relative == "checksums.sha256":
            continue
        path = root / relative
        if not path.exists():
            failures.append(f"missing {relative}")
        elif file_sha256(path) != expected:
            failures.append(relative)
    return failures


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")


def _write_spec_files(run_dir: Path, target: Path, manifest: dict[str, Any]) -> None:
    specs = {
        "feature_spec.yaml": {"features": manifest.get("feature_columns", [])},
        "label_spec.yaml": {"target": manifest.get("target"), "horizons": manifest.get("config", {}).get("model", {}).get("horizons", [])},
        "split_spec.yaml": {
            "train_fraction": manifest.get("config", {}).get("model", {}).get("train_fraction"),
            "validation_fraction": manifest.get("config", {}).get("model", {}).get("validation_fraction"),
        },
        "threshold_spec.yaml": {"cost_hurdle": manifest.get("config", {}).get("model", {}).get("cost_hurdle")},
        "model_grid.yaml": {"model": "standardized_logistic_regression", "max_iter": 500},
        "metric_spec.yaml": {"metrics": ["auc", "log_loss", "brier"]},
        "plot_policy.yaml": {"plots": ["prediction_distribution"], "bins": 20},
        "selected_model_policy.yaml": {"selection": "Gate 3 public validation only"},
    }
    for name, payload in specs.items():
        (target / name).write_text(yaml.safe_dump(payload, sort_keys=False))
