import pandas as pd

from bondsim.validation.medium import _gate_decision


class Frozen:
    calibration_id = "calibration-test"
    environment_deviations = []


def test_gate3_decision_has_approval_contract():
    recovery = pd.DataFrame(
        [
            {"scenario": "controlled_all", "metric": "public_reversal", "estimate": -0.06, "seed": seed}
            for seed in range(5)
        ]
        + [
            {"scenario": "controlled_all", "metric": "sign_persistence", "estimate": 0.5, "seed": seed}
            for seed in range(5)
        ]
        + [
            {"scenario": "controlled_all", "metric": "public_leader_to_follower", "estimate": 0.05, "seed": seed}
            for seed in range(5)
        ]
    )
    nulls = pd.DataFrame(
        [
            {"metric": "public_follower_to_leader", "estimate": 0.001},
            {"metric": "public_cross_issuer", "estimate": 0.001},
        ]
    )
    fidelity = pd.DataFrame({"oracle_accounting_passed": [True]})
    decision = _gate_decision(recovery, nulls, fidelity, Frozen())
    assert decision["calibration_id"] == "calibration-test"
    assert decision["approved_for_gate4"]


def test_gate3_reversal_uses_realized_oracle_target_when_available():
    recovery = pd.DataFrame(
        [
            {"scenario": "controlled_all", "metric": "public_reversal", "estimate": -0.176, "seed": seed}
            for seed in range(5)
        ]
        + [
            {"scenario": "controlled_all", "metric": "sign_persistence", "estimate": 0.5, "seed": seed}
            for seed in range(5)
        ]
        + [
            {"scenario": "controlled_all", "metric": "public_leader_to_follower", "estimate": 0.05, "seed": seed}
            for seed in range(5)
        ]
    )
    nulls = pd.DataFrame(
        [
            {"metric": "public_follower_to_leader", "estimate": 0.001},
            {"metric": "public_cross_issuer", "estimate": 0.001},
        ]
    )
    oracle_effects = pd.DataFrame(
        [
            {"scenario": "controlled_all", "metric": "oracle_reversal_target", "estimate": -0.15, "seed": seed}
            for seed in range(5)
        ]
    )
    fidelity = pd.DataFrame({"oracle_accounting_passed": [True]})
    decision = _gate_decision(recovery, nulls, fidelity, Frozen(), oracle_effects)
    reversal = decision["intended_effects"]["public_reversal"]
    assert reversal["target_magnitude"] == 0.15
    assert reversal["target_source"] == "truth-ledger realized large-print state contribution"
    assert reversal["magnitude_passed"]
    assert decision["approved_for_gate4"]
