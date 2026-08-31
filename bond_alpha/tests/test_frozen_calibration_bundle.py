import json

import pytest

from bondsim.calibration.freeze import freeze_calibration
from bondsim.calibration.frozen import load_frozen_calibration, verify_checksums


def _write_run(run):
    run.mkdir()
    for name in [
        "resolved_config.yaml",
        "seed_manifest.json",
        "source_fingerprint.json",
        "selected_models.json",
        "software_environment.json",
    ]:
        (run / name).write_text("{}")
    (run / "source_fingerprint.json").write_text(json.dumps({"fingerprint": "src"}))
    (run / "calibration_manifest.json").write_text(
        json.dumps(
            {
                "run_id": "run",
                "calibration_id": "calibration-test",
                "resolved_config_hash": "cfg",
                "gates": [],
                "hawkes": {},
                "liquidity": [],
                "synthcity": {},
            }
        )
    )
    checksums = []
    for path in sorted(p for p in run.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        import hashlib

        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(run)}")
    (run / "checksums.sha256").write_text("\n".join(checksums) + "\n")


def test_frozen_calibration_loads_and_verifies(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    frozen = freeze_calibration(run, tmp_path / "models")
    bundle = load_frozen_calibration("calibration-test", tmp_path / "models", expected_source_fingerprint="src", expected_config_hash="cfg")
    assert bundle.path == frozen
    assert verify_checksums(frozen) == []


def test_freeze_refuses_to_overwrite_without_force(tmp_path):
    run = tmp_path / "run"
    _write_run(run)
    freeze_calibration(run, tmp_path / "models")
    with pytest.raises(FileExistsError):
        freeze_calibration(run, tmp_path / "models")
