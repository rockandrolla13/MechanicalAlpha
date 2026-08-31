from bondsim.config import load_config
from bondsim.gate4 import verify_gate4_preconditions


def test_gate4_preflight_accepts_current_frozen_bundle():
    config = load_config("configs/gate4.yaml")
    result = verify_gate4_preconditions(config)
    assert result["approved_for_gate4"] is True
    assert result["calibration_id"] == "calibration-v1.0.0"
    assert result["checksum_failures"] == []
