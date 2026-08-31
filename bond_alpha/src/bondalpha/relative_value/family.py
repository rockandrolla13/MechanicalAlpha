"""Standalone relative-value alpha."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any


def default_relative_value_spec() -> dict[str, Any]:
    return {"value_key": "spread", "group_key": "sector", "clip": 3.0, "shrinkage": 0.25}


def build_relative_value_family(
    rows: Iterable[Mapping[str, Any]],
    *,
    value_key: str = "spread",
    group_key: str = "sector",
    clip: float = 3.0,
    shrinkage: float = 0.25,
) -> list[dict[str, Any]]:
    row_list = list(rows)
    grouped_values: dict[Any, list[float]] = defaultdict(list)
    for row in row_list:
        grouped_values[row.get(group_key)].append(float(row.get(value_key, 0.0)))
    group_centers = {group: median(values) for group, values in grouped_values.items()}
    outputs: list[dict[str, Any]] = []
    for row in row_list:
        group = row.get(group_key)
        gap = float(row.get(value_key, 0.0)) - group_centers[group]
        score = _clip(-(1.0 - shrinkage) * gap, clip)
        outputs.append({"date": row.get("date"), "asset_id": row.get("asset_id"), "alpha_family": "relative_value", "alpha_name": "relative_value_gap", "score": score, "direction": "long" if score > 0 else "short" if score < 0 else "flat", "metadata": {"group": group, "group_key": group_key, "group_center": group_centers[group], "shrinkage": shrinkage, "raw_gap": gap}})
    return outputs


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))
