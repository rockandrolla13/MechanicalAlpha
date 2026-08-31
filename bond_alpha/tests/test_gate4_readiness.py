import json

from bondsim.config import load_config
from bondsim.gate4_readiness import run_gate4_readiness_audit


def test_gate4_readiness_audit_writes_required_files():
    config = load_config("configs/gate4.yaml")
    result = run_gate4_readiness_audit(config)
    assert result["gate3_decision_found"] is True
    assert result["approved_for_gate4"] is True
    assert result["frozen_calibration_found"] is True
    assert result["checksums_valid"] is True
    assert result["public_truth_separation_valid"] is True
    assert result["gate3_public_data_available"] is True
    assert result["gate4_ready"] is True
    saved = json.loads((config.paths.report_root / "gate4" / "readiness_audit.json").read_text())
    assert saved["gate4_ready"] is True
