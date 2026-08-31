"""Output partition helpers for public and truth BondSim datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


FORBIDDEN_PUBLIC_COLUMNS = frozenset(
    {
        "source_bond_id",
        "source_issuer_id",
        "latent_fair_value",
        "ou_pressure",
        "permanent_impact_state",
        "ordinary_temporary_impact_state",
        "planted_large_print_state",
        "planted_leadlag_state",
        "latent_mid_without_planted_effects",
        "latent_mid_with_planted_effects",
        "transaction_concession",
        "observation_noise",
        "hawkes_cluster_id",
        "hawkes_parent_event_id",
        "hawkes_generation",
        "hawkes_edge_class",
        "is_immigrant",
        "large_print_threshold",
        "is_large_print",
        "source_leader_event_id",
        "planted_effect_ids",
    }
)


@dataclass(frozen=True)
class PartitionSpec:
    """A single year/month partition target."""

    year: int
    month: int
    path: Path
    rows: int


def monthly_partition_path(root: Path, dataset: str, year: int, month: int, part: int = 0) -> Path:
    """Return a true calendar year/month partition path."""

    if not 1 <= int(month) <= 12:
        raise ValueError(f"month must be in 1..12, got {month}")
    return root / dataset / f"year={int(year):04d}" / f"month={int(month):02d}" / f"part-{int(part):04d}.parquet"


def partition_frame_by_month(
    frame: pd.DataFrame,
    root: Path,
    dataset: str,
    timestamp_col: str = "timestamp_utc",
) -> list[tuple[PartitionSpec, pd.DataFrame]]:
    """Split a frame into deterministic calendar month partitions."""

    if timestamp_col not in frame.columns:
        raise KeyError(f"missing timestamp column: {timestamp_col}")
    if frame.empty:
        return []
    working = frame.copy()
    timestamps = pd.to_datetime(working[timestamp_col], utc=True)
    working["_partition_year"] = timestamps.dt.year.astype(int)
    working["_partition_month"] = timestamps.dt.month.astype(int)
    partitions: list[tuple[PartitionSpec, pd.DataFrame]] = []
    for (year, month), group in working.groupby(["_partition_year", "_partition_month"], sort=True):
        clean = group.drop(columns=["_partition_year", "_partition_month"])
        spec = PartitionSpec(
            year=int(year),
            month=int(month),
            path=monthly_partition_path(root, dataset, int(year), int(month)),
            rows=int(len(clean)),
        )
        partitions.append((spec, clean.reset_index(drop=True)))
    return partitions


def write_monthly_partitions(
    frame: pd.DataFrame,
    root: Path,
    dataset: str,
    timestamp_col: str = "timestamp_utc",
    compression: str = "zstd",
) -> list[PartitionSpec]:
    """Write true year/month partitions and return their specs."""

    specs: list[PartitionSpec] = []
    for spec, part in partition_frame_by_month(frame, root, dataset, timestamp_col):
        spec.path.parent.mkdir(parents=True, exist_ok=True)
        part.to_parquet(spec.path, index=False, compression=compression)
        specs.append(spec)
    return specs


def assert_public_schema_is_clean(columns: Iterable[str]) -> None:
    """Protect public output from truth and source-identifier columns."""

    leaked = sorted(FORBIDDEN_PUBLIC_COLUMNS.intersection(set(columns)))
    if leaked:
        raise ValueError(f"public output contains forbidden columns: {leaked}")
