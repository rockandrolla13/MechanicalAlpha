"""Standalone flow-persistence alpha."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def default_flow_spec() -> dict[str, Any]:
    return {"horizons": (3, 5, 10), "weights": None, "clip": 3.0, "flow_key": "net_flow", "stability_key": "trade_count"}


def build_flow_persistence_family(
    rows: Iterable[Mapping[str, Any]],
    *,
    horizons: Iterable[int] = (3, 5, 10),
    weights: Iterable[float] | None = None,
    clip: float = 3.0,
    flow_key: str = "net_flow",
    stability_key: str = "trade_count",
) -> list[dict[str, Any]]:
    horizon_list = tuple(horizons)
    weight_list = _normalise_weights(horizon_list, weights)
    outputs: list[dict[str, Any]] = []
    for row in rows:
        components = {
            f"flow_{horizon}d": float(row.get(f"{flow_key}_{horizon}d", row.get(flow_key, 0.0))) * weight
            for horizon, weight in zip(horizon_list, weight_list)
        }
        stability = max(float(row.get(stability_key, 1.0)), 1.0)
        score = _clip(sum(components.values()) * min(1.0, stability / 10.0), clip)
        outputs.append(_alpha_row(row, "flow_persistence", "flow_persistence_blend", score, {"horizons": horizon_list, "weights": weight_list, "components": components}))
    return outputs


def _normalise_weights(keys: tuple[int, ...], weights: Iterable[float] | None) -> list[float]:
    if not keys:
        raise ValueError("horizons must not be empty")
    if weights is None:
        return [1.0 / len(keys)] * len(keys)
    values = [float(weight) for weight in weights]
    if len(values) != len(keys):
        raise ValueError("weights must align with horizons")
    total = sum(abs(value) for value in values)
    if total == 0:
        raise ValueError("weights must not all be zero")
    return [value / total for value in values]


def _alpha_row(row: Mapping[str, Any], family: str, name: str, score: float, metadata: dict[str, Any]) -> dict[str, Any]:
    return {"date": row.get("date"), "asset_id": row.get("asset_id"), "alpha_family": family, "alpha_name": name, "score": score, "direction": "long" if score > 0 else "short" if score < 0 else "flat", "metadata": metadata}


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))
