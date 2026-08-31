"""Scenario switches for controlled effects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioFlags:
    reversal: bool
    sign_persistence: bool
    leadlag: bool
    calibrated_realism: bool = False


def flags_for(name: str) -> ScenarioFlags:
    if name == "controlled_all":
        return ScenarioFlags(True, True, True)
    if name == "controlled_null":
        return ScenarioFlags(False, False, False)
    if name == "reversal_only":
        return ScenarioFlags(True, False, False)
    if name == "sign_only":
        return ScenarioFlags(False, True, False)
    if name == "leadlag_only":
        return ScenarioFlags(False, False, True)
    if name == "calibrated_realism":
        return ScenarioFlags(True, True, True, calibrated_realism=True)
    raise ValueError(f"Unknown scenario: {name}")
