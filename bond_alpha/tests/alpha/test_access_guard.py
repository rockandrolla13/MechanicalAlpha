from pathlib import Path

import pytest

from bondalpha.access_guard import assert_no_truth_columns, assert_public_path


def test_truth_path_is_rejected():
    with pytest.raises(PermissionError):
        assert_public_path(Path("data/synthetic_truth/gate4/run"))


def test_truth_columns_are_rejected():
    with pytest.raises(PermissionError):
        assert_no_truth_columns(["event_id", "latent_mid_with_planted_effects"])


def test_public_columns_are_allowed():
    assert_no_truth_columns(["event_id", "price", "notional", "side"])
