import pytest

from bondsim.config import load_config
from bondsim.validation.medium import run_medium_gate


def test_gate3_requires_frozen_calibration_id():
    config = load_config("configs/base.yaml")
    config.frozen_calibration_id = None
    with pytest.raises(RuntimeError, match="frozen_calibration_id"):
        run_medium_gate(config)
