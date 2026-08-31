"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    name: str
    master_seed: int = 20260830
    timezone: str = "UTC"
    session_open: str = "09:30:00"
    session_close: str = "16:00:00"


class PathConfig(BaseModel):
    data_root: str = "data/raw"
    processed_root: Path = Path("data/processed")
    model_root: Path = Path("models")
    synthetic_root: Path = Path("data/synthetic")
    truth_root: Path = Path("data/synthetic_truth")
    report_root: Path = Path("reports")


class SplitConfig(BaseModel):
    train_fraction: float = 0.70
    validation_fraction: float = 0.15
    test_fraction: float = 0.15
    minimum_test_sessions: int = 60


class UniverseConfig(BaseModel):
    n_bonds: int = 500
    target_issuers: int = 100
    minimum_issuers_with_three_bonds: int = 70


class LiquidityConfig(BaseModel):
    target_median_events_per_day: float = 2.0
    target_p10_events_per_day: float = 0.4
    maximum_events_per_day: float = 25.0
    pilot_sessions: int = 60
    calibration_iterations: int = 4
    calibration_damping: float = 0.5


class HawkesConfig(BaseModel):
    decay_half_lives_minutes: list[float] = Field(default_factory=lambda: [5, 30, 120])
    maximum_spectral_radius: float = 0.85
    controlled_target_spectral_radius: float = 0.70
    reset_excitation_at_session_close: bool = True
    likelihood_l2_penalty: float = 0.001
    use_likelihood_refinement: bool = False


class ActivityConfig(BaseModel):
    intraday_bucket_minutes: int = 30
    daily_model: str = "block_bootstrap"
    block_length_sessions: int = 5
    include_sector_factors: bool = False


class MarksConfig(BaseModel):
    synthcity_candidates: list[str] = Field(default_factory=lambda: ["arf", "tvae", "ctgan"])
    quick_candidates: list[str] = Field(default_factory=lambda: ["arf"])
    large_print_quantile: float = 0.90
    tail_model_threshold_quantile: float = 0.95
    minimum_stratum_rows: int = 100
    pre_generated_pool_size: int = 5000
    maximum_generation_retries: int = 5
    empirical_fallback: bool = True
    prohibit_raw_identifiers: bool = True
    prohibit_future_features: bool = True


class PriceConfig(BaseModel):
    fair_value_route: str = "transaction_price_proxy"
    ou_min_half_life_days: float = 0.25
    ou_max_half_life_days: float = 20.0
    innovation_distribution: str = "empirical"
    use_duration_convexity_when_available: bool = False
    factor_bootstrap_block_sessions: int = 5


class SimulationConfig(BaseModel):
    n_sessions: int = 756
    smoke_bonds: int = 10
    smoke_sessions: int = 20
    medium_bonds: int = 100
    medium_sessions: int = 100
    output_partition_columns: list[str] = Field(default_factory=lambda: ["scenario", "year", "month"])
    parquet_compression: str = "zstd"
    stream_by_session: bool = True
    max_events_per_session_safety: int = 100000


class ValidationConfig(BaseModel):
    recovery_seeds: int = 5
    relative_effect_tolerance: float = 0.25
    null_fraction_of_controlled_max: float = 0.20
    holm_alpha: float = 0.05
    liquidity_median_range: tuple[float, float] = (1.90, 2.10)
    liquidity_p10_range: tuple[float, float] = (0.36, 0.44)


class BondSimConfig(BaseModel):
    project: ProjectConfig
    paths: PathConfig
    columns: dict[str, Any] = Field(default_factory=dict)
    split: SplitConfig = Field(default_factory=SplitConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    liquidity: LiquidityConfig = Field(default_factory=LiquidityConfig)
    hawkes: HawkesConfig = Field(default_factory=HawkesConfig)
    activity: ActivityConfig = Field(default_factory=ActivityConfig)
    marks: MarksConfig = Field(default_factory=MarksConfig)
    prices: PriceConfig = Field(default_factory=PriceConfig)
    positive_controls: dict[str, Any] = Field(default_factory=dict)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    scenario: str = "controlled_all"
    frozen_calibration_id: str | None = None


_ENV_PATTERN = re.compile(r"\$\{([^}:]+):-([^}]+)\}")


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
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        elif key != "inherits":
            merged[key] = value
    return merged


def load_config(path: str | Path) -> BondSimConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text()) or {}
    if "inherits" in raw:
        parent = config_path.parent / raw["inherits"]
        parent_raw = yaml.safe_load(parent.read_text()) or {}
        raw = _deep_merge(parent_raw, raw)
    return BondSimConfig.model_validate(_expand_env(raw))


def write_resolved_config(config: BondSimConfig) -> Path:
    path = config.paths.model_root / "resolved_config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    return path
