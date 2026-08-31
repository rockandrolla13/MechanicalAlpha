"""Composite index for standalone alpha outputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def default_composite_spec() -> dict[str, Any]:
    return {"family_weights": {"reversal": 1.0, "flow_persistence": 1.0, "lead_lag": 1.0, "relative_value": 1.0}, "selection_size": 25}


def build_composite_scaffold(
    family_outputs: Iterable[Mapping[str, Any]],
    *,
    family_weights: Mapping[str, float] | None = None,
    selection_size: int | None = None,
) -> dict[str, Any]:
    weights = dict(family_weights or default_composite_spec()["family_weights"])
    grouped: dict[tuple[Any, Any], list[Mapping[str, Any]]] = defaultdict(list)
    for row in family_outputs:
        grouped[(row.get("date"), row.get("asset_id"))].append(row)
    candidates: list[dict[str, Any]] = []
    for (date, asset_id), rows in grouped.items():
        weighted_sum = 0.0
        total_weight = 0.0
        components: dict[str, float] = {}
        for row in rows:
            family = str(row.get("alpha_family"))
            weight = float(weights.get(family, 1.0))
            score = float(row.get("score", 0.0))
            weighted_sum += weight * score
            total_weight += abs(weight)
            components[family] = score
        composite_score = weighted_sum / total_weight if total_weight else 0.0
        candidates.append({"date": date, "asset_id": asset_id, "alpha_family": "composite", "alpha_name": "alpha_factory_composite", "score": composite_score, "direction": "long" if composite_score > 0 else "short" if composite_score < 0 else "flat", "metadata": {"component_count": len(rows), "family_weights": weights, "components": components}})
    ranked = sorted(candidates, key=lambda item: abs(float(item["score"])), reverse=True)
    if selection_size is not None:
        ranked = ranked[:selection_size]
    return {"candidates": ranked, "selection_size": selection_size, "family_weights": weights}
