"""Public synthetic dataset loading for Alpha Factory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bondalpha.access_guard import assert_no_truth_columns, assert_public_path


@dataclass(frozen=True)
class PublicSyntheticDataset:
    root: Path
    trades: pd.DataFrame
    bonds: pd.DataFrame
    scenario_roots: list[Path]


def load_public_synthetic(root: str | Path) -> PublicSyntheticDataset:
    """Load public synthetic scenario outputs without touching truth data."""

    root = Path(root)
    assert_public_path(root)
    scenario_roots = _scenario_roots(root)
    if not scenario_roots:
        raise FileNotFoundError(f"no public synthetic scenario roots found under {root}")
    trades = []
    bonds = []
    for scenario_root in scenario_roots:
        assert_public_path(scenario_root)
        scenario = scenario_root.name.removeprefix("scenario=")
        for path in sorted((scenario_root / "trades").glob("year=*/month=*/part-*.parquet")):
            assert_public_path(path)
            frame = pd.read_parquet(path)
            frame["scenario"] = scenario
            frame["scenario_root"] = str(scenario_root)
            trades.append(frame)
        bond_path = scenario_root / "bonds.parquet"
        if bond_path.exists():
            bond_frame = pd.read_parquet(bond_path)
            bond_frame["scenario"] = scenario
            bonds.append(bond_frame)
    if not trades:
        raise FileNotFoundError(f"no public trade partitions found under {root}")
    trade_frame = pd.concat(trades, ignore_index=True)
    bond_frame = pd.concat(bonds, ignore_index=True) if bonds else pd.DataFrame()
    assert_no_truth_columns(trade_frame.columns)
    assert_no_truth_columns(bond_frame.columns)
    return PublicSyntheticDataset(root=root, trades=trade_frame, bonds=bond_frame, scenario_roots=scenario_roots)


def _scenario_roots(root: Path) -> list[Path]:
    if root.name.startswith("scenario=") and (root / "trades").exists():
        return [root]
    direct = sorted(path for path in root.glob("scenario=*") if (path / "trades").exists())
    if direct:
        return direct
    medium = sorted(path for path in root.glob("seed=*/synthetic/scenario=*") if (path / "trades").exists())
    if medium:
        return medium
    gate4 = sorted(path for path in root.glob("*/scenario=*") if (path / "trades").exists())
    return gate4
