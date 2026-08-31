"""Standalone issuer lead-lag alpha."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def default_lead_lag_spec() -> dict[str, Any]:
    return {"pairs": (("equity_move", "credit_move"), ("etf_move", "cash_move")), "clip": 3.0, "lag_scale": 1.0}


def build_lead_lag_family(
    rows: Iterable[Mapping[str, Any]],
    *,
    pairs: Iterable[tuple[str, str]] = (("equity_move", "credit_move"), ("etf_move", "cash_move")),
    clip: float = 3.0,
    lag_scale: float = 1.0,
) -> list[dict[str, Any]]:
    pair_list = tuple(pairs)
    if not pair_list:
        raise ValueError("pairs must not be empty")
    outputs: list[dict[str, Any]] = []
    for row in rows:
        components = {
            f"{leader_key}_minus_{follower_key}": (float(row.get(leader_key, 0.0)) - float(row.get(follower_key, 0.0))) * lag_scale
            for leader_key, follower_key in pair_list
        }
        score = _clip(sum(components.values()) / len(pair_list), clip)
        outputs.append({"date": row.get("date"), "asset_id": row.get("asset_id"), "alpha_family": "lead_lag", "alpha_name": "lead_lag_blend", "score": score, "direction": "long" if score > 0 else "short" if score < 0 else "flat", "metadata": {"pairs": pair_list, "lag_scale": lag_scale, "components": components}})
    return outputs


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))
