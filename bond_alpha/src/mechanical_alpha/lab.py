"""Thin notebook control-panel helpers for simulator and alpha smoke runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bondsim.cli import main as bondsim_main
from mechanical_alpha.analysis import portfolio_pnl_hooks, summarize_signals_by_alpha
from mechanical_alpha.cli import main as mechanical_alpha_main
from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.data.synthetic import load_synthetic_bundle


DEFAULT_SYNTHETIC_ROOT = Path("data/synthetic")
DEFAULT_LAB_OUTPUT = Path("reports/lab/standalone_alpha_signals.parquet")


@dataclass(frozen=True)
class LabRun:
    """Notebook-facing result for a standalone alpha smoke run."""

    scenario_root: Path
    alpha_ids: tuple[str, ...]
    output_path: Path
    signals: pd.DataFrame
    summary: pd.DataFrame
    hooks: dict[str, object]


def discover_synthetic_scenarios(root: str | Path = DEFAULT_SYNTHETIC_ROOT) -> pd.DataFrame:
    """List existing public synthetic scenario roots."""

    base = Path(root)
    rows: list[dict[str, object]] = []
    for scenario_root in sorted(base.glob("scenario=*")):
        if _is_public_scenario_root(scenario_root):
            rows.append(_scenario_row(scenario_root))
    for scenario_root in sorted((base / "gate4").glob("gate4-*/scenario=*")):
        if _is_public_scenario_root(scenario_root):
            row = _scenario_row(scenario_root)
            row["gate4_run_id"] = scenario_root.parent.name
            rows.append(row)
    columns = ["scenario", "scenario_root", "gate4_run_id", "has_external_factors"]
    return pd.DataFrame(rows, columns=columns).sort_values(["scenario", "scenario_root"]).reset_index(drop=True)


def resolve_scenario_root(
    scenario: str = "controlled_all",
    *,
    root: str | Path = DEFAULT_SYNTHETIC_ROOT,
    gate4_run_id: str | None = None,
) -> Path:
    """Resolve an existing synthetic scenario root by name."""

    base = Path(root)
    scenario_name = scenario if scenario.startswith("scenario=") else f"scenario={scenario}"
    candidates = [base / scenario_name]
    if gate4_run_id is not None:
        candidates.insert(0, base / "gate4" / gate4_run_id / scenario_name)
    for candidate in candidates:
        if _is_public_scenario_root(candidate):
            return candidate
    available = discover_synthetic_scenarios(base)
    known = ", ".join(available["scenario"].drop_duplicates().astype(str).tolist())
    raise FileNotFoundError(f"missing synthetic scenario root for {scenario_name}; available scenarios: {known}")


def load_synthetic_scenario(scenario_root: str | Path) -> AlphaInputBundle:
    """Load one existing public synthetic scenario as an alpha input bundle."""

    return load_synthetic_bundle(scenario_root)


def load_simulation_public_data(scenario_root: str | Path) -> dict[str, object]:
    """Load one public synthetic scenario and return notebook-ready tables."""

    bundle = load_synthetic_scenario(scenario_root)
    signal_grid = (
        bundle.events[["prediction_timestamp", "bond_id", "issuer_id"]]
        .drop_duplicates()
        .sort_values(["bond_id", "prediction_timestamp"])
        .reset_index(drop=True)
    )
    summary = pd.DataFrame(
        [
            {
                "rows": int(len(bundle.events)),
                "bonds": int(bundle.events["bond_id"].nunique()) if "bond_id" in bundle.events.columns else 0,
                "issuers": int(bundle.events["issuer_id"].nunique()) if "issuer_id" in bundle.events.columns else 0,
                "sessions": int(bundle.events["session_date"].nunique()) if "session_date" in bundle.events.columns else 0,
            }
        ]
    )
    return {
        "bonds": bundle.bonds,
        "events": bundle.events,
        "signal_grid": signal_grid,
        "summary": summary,
    }


def run_bondsim_cli(args: Sequence[str]) -> int:
    """Call the existing ``bondsim`` CLI entry point from a notebook cell."""

    return bondsim_main(list(args))


def run_mechanical_alpha_cli(args: Sequence[str]) -> int:
    """Call the existing ``mechanical-alpha`` CLI entry point from a notebook cell."""

    return mechanical_alpha_main(list(args))


def run_standalone_alphas(
    scenario_root: str | Path,
    alpha_ids: Sequence[str],
    *,
    output_path: str | Path = DEFAULT_LAB_OUTPUT,
) -> LabRun:
    """Run selected standalone alphas through the existing alpha CLI and summarize them."""

    root = Path(scenario_root)
    output = Path(output_path)
    selected = tuple(str(alpha_id) for alpha_id in alpha_ids)
    if not selected:
        raise ValueError("alpha_ids must not be empty")

    run_mechanical_alpha_cli(
        [
            "compute",
            "--synthetic-root",
            str(root),
            "--alphas",
            ",".join(selected),
            "--output",
            str(output),
        ]
    )
    signals = pd.read_parquet(output)
    summary = summarize_signals_by_alpha(signals)
    return LabRun(
        scenario_root=root,
        alpha_ids=selected,
        output_path=output,
        signals=signals,
        summary=summary,
        hooks=portfolio_pnl_hooks(signals, summary),
    )


def compute_alpha_signals(
    scenario_root: str | Path,
    *,
    alphas: Sequence[str] = ("A1", "A2", "A3"),
    output_path: str | Path = DEFAULT_LAB_OUTPUT,
) -> pd.DataFrame:
    """Compute selected standalone alphas and return the stacked signal frame."""

    return run_standalone_alphas(scenario_root, alphas, output_path=output_path).signals


def signal_summary(signals: pd.DataFrame) -> pd.DataFrame:
    """Summarize a stacked standalone-alpha signal frame."""

    return summarize_signals_by_alpha(signals)


def smoke_alpha_lab(
    scenario: str = "controlled_all",
    alpha_ids: Sequence[str] = ("A1", "A2", "A3"),
    *,
    synthetic_root: str | Path = DEFAULT_SYNTHETIC_ROOT,
    output_path: str | Path = DEFAULT_LAB_OUTPUT,
) -> LabRun:
    """Resolve a scenario, run selected alphas, and return notebook-ready tables."""

    scenario_root = resolve_scenario_root(scenario, root=synthetic_root)
    return run_standalone_alphas(scenario_root, alpha_ids, output_path=output_path)


def _is_public_scenario_root(path: Path) -> bool:
    return path.is_dir() and (path / "bonds.parquet").exists() and any((path / "trades").glob("year=*/month=*/part-*.parquet"))


def _scenario_row(path: Path) -> dict[str, object]:
    return {
        "scenario": path.name.removeprefix("scenario="),
        "scenario_root": str(path),
        "gate4_run_id": None,
        "has_external_factors": bool((path / "external_factors.parquet").exists()),
    }
