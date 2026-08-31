"""Alpha Factory configuration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AlphaPaths(BaseModel):
    gate3_public_root: Path = Path("data/medium")
    run_root: Path = Path("runs/alpha")
    frozen_root: Path = Path("models/alpha_frozen")
    report_root: Path = Path("reports/alpha")


class AlphaModelConfig(BaseModel):
    horizons: list[str] = Field(default_factory=lambda: ["30m", "2h", "1d"])
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    cost_hurdle: float = 0.03
    random_seed: int = 20260830


class AlphaFactoryConfig(BaseModel):
    project: str = "alpha_factory_v1"
    paths: AlphaPaths = Field(default_factory=AlphaPaths)
    model: AlphaModelConfig = Field(default_factory=AlphaModelConfig)
    features: list[str] = Field(
        default_factory=lambda: [
            "reversal_pressure",
            "flow_persistence",
            "leader_follower_pressure",
            "relative_value_gap",
            "liquidity_control",
        ]
    )
    forbidden_columns: list[str] = Field(default_factory=lambda: ["truth", "latent_", "planted_"])


_ENV_PATTERN = re.compile(r"\$\{([^}:]+):-([^}]+)\}")


def load_alpha_config(path: str | Path) -> AlphaFactoryConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    if "inherits" in raw:
        parent = Path(path).parent / raw["inherits"]
        base = yaml.safe_load(parent.read_text()) or {}
        raw = _deep_merge(base, raw)
    return AlphaFactoryConfig.model_validate(_expand_env(raw))


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(2)), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key == "inherits":
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
