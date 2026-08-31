from dataclasses import dataclass

from bondsim.calibration.ensemble import synthcity_fit_stability


@dataclass
class Selection:
    selected: str = "empirical_fallback"
    candidates: list[dict[str, object]] = None


def test_empirical_fallback_stability_record():
    record = synthcity_fit_stability(Selection(candidates=[]))
    assert record["maximum_validation_score_dispersion"] == 0.0
