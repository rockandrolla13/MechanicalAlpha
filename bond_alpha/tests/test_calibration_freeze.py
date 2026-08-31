import json
import hashlib

from bondsim.calibration.freeze import freeze_calibration


def test_freeze_requires_manifest_and_creates_bundle(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    for name in [
        "resolved_config.yaml",
        "seed_manifest.json",
        "source_fingerprint.json",
        "selected_models.json",
        "software_environment.json",
    ]:
        (run / name).write_text("{}")
    (run / "calibration_manifest.json").write_text(json.dumps({"gates": [], "calibration_id": "calibration-test"}))
    checksums = []
    for path in sorted(p for p in run.rglob("*") if p.is_file()):
        checksums.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(run)}")
    (run / "checksums.sha256").write_text("\n".join(checksums) + "\n")
    frozen = freeze_calibration(run, tmp_path / "models")
    assert (frozen / "FROZEN").exists()
