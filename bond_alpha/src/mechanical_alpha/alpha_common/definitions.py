"""Small metadata objects shared by standalone alpha files."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FeatureDefinition:
    """Static metadata for one alpha file."""

    feature_id: str
    formula: str
    source_fields: tuple[str, ...]
    clock: str
    window: str
    min_observations: int
    missing_policy: str
    expected_sign: str
    feature_class: str
    point_in_time_dependencies: tuple[str, ...]
    computational_cost: str
    version: str = "0.1.0"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

