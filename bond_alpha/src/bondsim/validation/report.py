"""Structural validation and report writing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from bondsim.config import BondSimConfig
from bondsim.schema import PUBLIC_TRADE_COLUMNS, TRUTH_COLUMNS


def validate_outputs(
    trades: pd.DataFrame,
    truth: pd.DataFrame,
    bonds: pd.DataFrame,
    config: BondSimConfig,
    scenario: str,
    mode: str,
) -> dict[str, object]:
    if mode == "smoke":
        expected_bonds = config.simulation.smoke_bonds
    elif mode == "medium":
        expected_bonds = config.simulation.medium_bonds
    else:
        expected_bonds = config.universe.n_bonds
    failures: list[str] = []
    if len(bonds) != expected_bonds:
        failures.append(f"expected {expected_bonds} bonds, found {len(bonds)}")
    if trades["event_id"].duplicated().any():
        failures.append("duplicate public event_id")
    if truth["event_id"].duplicated().any():
        failures.append("duplicate truth event_id")
    if not set(trades["side"].unique()).issubset({-1, 1}):
        failures.append("invalid side values")
    if (trades["notional"] < 0).any():
        failures.append("negative notionals")
    if not np.isfinite(trades["price"]).all() or (trades["price"] <= 0).any():
        failures.append("nonpositive or nonfinite prices")
    if trades[PUBLIC_TRADE_COLUMNS].isna().any().any():
        failures.append("NaN in public output")
    public_forbidden = {"latent_fair_value", "source_bond_id", "source_issuer_id", "planted_large_print_state"}
    leaked = public_forbidden & set(trades.columns)
    if leaked:
        failures.append(f"public output leaked forbidden columns: {sorted(leaked)}")
    if not set(TRUTH_COLUMNS).issubset(truth.columns):
        failures.append("truth output missing required columns")
    return {
        "scenario": scenario,
        "mode": mode,
        "passed": not failures,
        "failures": failures,
        "public_rows": int(len(trades)),
        "truth_rows": int(len(truth)),
        "bond_rows": int(len(bonds)),
    }


def write_reports(root: Path, validation: dict[str, object], extra: dict[str, object]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    fidelity = root / "fidelity"
    fidelity.mkdir(parents=True, exist_ok=True)
    (root / "calibration_summary.md").write_text(_simple_report("Calibration Summary", extra))
    (root / "hawkes_fit.md").write_text(_simple_report("Hawkes Fit", extra.get("hawkes", {})))
    (root / "price_model_fit.md").write_text(_simple_report("Price Model Fit", extra.get("prices", {})))
    (root / "positive_controls.md").write_text(
        _simple_report(
            "Positive Controls",
            {
                "truth": extra.get("truth", {}),
                "recovery": extra.get("recovery", {}),
            },
        )
    )
    (root / "privacy.md").write_text(
        "# Privacy\n\nNo source identifiers are included in public synthetic output. No differential-privacy claim is made.\n"
    )
    (root / "run_manifest.md").write_text(_simple_report("Run Manifest", {**extra, "validation": validation}))
    (fidelity / "summary.md").write_text(_simple_report("Fidelity Summary", validation))


def write_fidelity_plots(root: Path, trades: pd.DataFrame, truth: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import seaborn as sns

    fidelity = root / "fidelity"
    fidelity.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")
    plots = [
        ("liquidity_rates.png", trades.groupby("synthetic_bond_id")["event_id"].count(), "Events per synthetic bond"),
        ("intraday_activity.png", pd.to_datetime(trades["timestamp_utc"]).dt.hour.value_counts().sort_index(), "Events by hour"),
        ("notional_distribution.png", trades["notional"], "Synthetic notional"),
        ("price_distribution.png", trades["price"], "Synthetic price"),
        ("large_print_state.png", truth["planted_large_print_state"], "Planted large-print state"),
    ]
    for filename, series, title in plots:
        fig, ax = plt.subplots(figsize=(7, 4))
        values = pd.Series(series).replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            values = pd.Series([0.0])
        if filename == "intraday_activity.png":
            values.plot(kind="bar", ax=ax)
        else:
            sns.histplot(values, ax=ax, bins=30)
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(fidelity / filename)
        plt.close(fig)


def _simple_report(title: str, payload: object) -> str:
    return f"# {title}\n\n```text\n{payload}\n```\n"
