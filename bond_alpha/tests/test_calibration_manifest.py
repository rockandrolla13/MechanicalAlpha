from bondsim.calibration.ensemble import calibration_run_id
from bondsim.config import load_config


def test_calibration_run_id_is_deterministic():
    config = load_config("configs/base.yaml")
    splits = {"train": {"start": "2024-01-01", "end": "2024-02-01"}, "validation": {"start": "2024-02-02", "end": "2024-03-01"}}
    left = calibration_run_id(config, "cfg", "src", splits, "commit")
    right = calibration_run_id(config, "cfg", "src", splits, "commit")
    assert left == right
    assert left.startswith("cal-")
