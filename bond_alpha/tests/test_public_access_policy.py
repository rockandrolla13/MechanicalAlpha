from pathlib import Path

import pytest

from mechanical_alpha.public_policy import (
    FORBIDDEN_PUBLIC_COLUMNS,
    assert_no_truth_columns,
    assert_public_columns,
    assert_public_path,
)


def test_public_policy_blocks_truth_paths_and_columns():
    with pytest.raises(PermissionError):
        assert_public_path(Path("data/synthetic_truth/gate4/run"))

    with pytest.raises(PermissionError):
        assert_no_truth_columns(["event_id", "latent_mid_with_planted_effects"])

    with pytest.raises(ValueError):
        assert_public_columns(["event_id", "source_bond_id"])

    assert "source_bond_id" in FORBIDDEN_PUBLIC_COLUMNS
    assert_public_path(Path("data/released/gate4_public/run"))
    assert_no_truth_columns(["event_id", "price", "notional", "side"])
    assert_public_columns(["event_id", "price", "notional", "side"])
