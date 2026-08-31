import pandas as pd

from bondsim.calibration.metrics import canonical_table_hash


def test_same_seed_content_hash_ignores_row_order():
    left = pd.DataFrame({"event_id": ["b", "a"], "value": [2, 1]})
    right = pd.DataFrame({"value": [1, 2], "event_id": ["a", "b"]})
    assert canonical_table_hash(left, ["event_id"]) == canonical_table_hash(right, ["event_id"])
