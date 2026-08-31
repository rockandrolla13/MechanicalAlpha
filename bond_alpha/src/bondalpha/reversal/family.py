"""Standalone large-print reversal alpha."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def default_reversal_spec() -> dict[str, Any]:
    return {"lookbacks": (1, 3, 5), "weights": None, "clip": 3.0, "price_key": "price_return", "liquidity_key": "turnover"}


def build_reversal_family(
    rows: Iterable[Mapping[str, Any]],
    *,
    lookbacks: Iterable[int] = (1, 3, 5),
    weights: Iterable[float] | None = None,
    clip: float = 3.0,
    price_key: str = "price_return",
    liquidity_key: str = "turnover",
) -> list[dict[str, Any]]:
    lookback_list = tuple(lookbacks)
    weight_list = _normalise_weights(lookback_list, weights)
    outputs: list[dict[str, Any]] = []
    for row in rows:
        components: dict[str, float] = {}
        for lookback, weight in zip(lookback_list, weight_list):
            raw_move = float(row.get(f"{price_key}_{lookback}d", row.get(price_key, 0.0)))
            components[f"reversal_{lookback}d"] = -raw_move * weight
        liquidity = max(float(row.get(liquidity_key, 1.0)), 1e-9)
        score = _clip(sum(components.values()) / liquidity**0.5, clip)
        outputs.append(_alpha_row(row, "reversal", "reversal_blend", score, {"lookbacks": lookback_list, "weights": weight_list, "components": components}))
    return outputs


def _normalise_weights(keys: tuple[int, ...], weights: Iterable[float] | None) -> list[float]:
    if not keys:
        raise ValueError("lookbacks must not be empty")
    if weights is None:
        return [1.0 / len(keys)] * len(keys)
    values = [float(weight) for weight in weights]
    if len(values) != len(keys):
        raise ValueError("weights must align with lookbacks")
    total = sum(abs(value) for value in values)
    if total == 0:
        raise ValueError("weights must not all be zero")
    return [value / total for value in values]


def _alpha_row(row: Mapping[str, Any], family: str, name: str, score: float, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": row.get("date"),
        "asset_id": row.get("asset_id"),
        "alpha_family": family,
        "alpha_name": name,
        "score": score,
        "direction": "long" if score > 0 else "short" if score < 0 else "flat",
        "metadata": metadata,
    }


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))
