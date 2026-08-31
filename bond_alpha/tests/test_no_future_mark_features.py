from bondsim.calibration.gates import MARK_FIELDS


def test_mark_fields_exclude_future_and_truth_columns():
    assert all(not field.startswith(("future_", "target_", "label_", "latent_", "planted_", "hawkes_")) for field in MARK_FIELDS)
