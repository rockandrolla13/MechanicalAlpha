from __future__ import annotations

from bondsim.cli import main


def test_gate4_production_command_requires_config() -> None:
    try:
        main(["gate4-production", "--config", "configs/does-not-exist.yaml"])
    except FileNotFoundError:
        return
    raise AssertionError("gate4-production should try to load the supplied config")
