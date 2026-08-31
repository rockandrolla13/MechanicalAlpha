import pandas as pd

from bondsim.calibration.metrics import ensemble_summary


def test_metric_reproducibility():
    metrics = pd.DataFrame({"seed": [1, 2], "median_bond_event_rate": [2.0, 2.1]})
    pd.testing.assert_frame_equal(ensemble_summary(metrics), ensemble_summary(metrics))
