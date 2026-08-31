import pandas as pd

from bondsim.calibration.gates import leakage_audit
from bondsim.config import load_config


def test_no_test_leakage_audit_passes(tmp_path):
    events = pd.DataFrame(
        {
            "session_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "split": ["train", "validation", "test"],
            "side": [1, -1, 1],
            "log_notional": [1.0, 2.0, 3.0],
        }
    )
    assert leakage_audit(events, load_config("configs/base.yaml"), tmp_path)["passed"]
