"""Deterministic Alpha Factory report writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


def write_alpha_report(run_dir: Path, metrics: dict[str, Any], predictions: pd.DataFrame) -> Path:
    reports = run_dir / "reports"
    figures = run_dir / "figures"
    plot_data = run_dir / "plot_data"
    reports.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    plot_data.mkdir(parents=True, exist_ok=True)
    predictions[["event_id", "timestamp_utc", "prediction"]].to_parquet(plot_data / "prediction_distribution.parquet", index=False)
    fig, ax = plt.subplots(figsize=(7, 4))
    predictions["prediction"].hist(ax=ax, bins=20)
    ax.set_title("Alpha prediction distribution")
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Event count")
    fig.tight_layout()
    fig.savefig(figures / "prediction_distribution.png")
    fig.savefig(figures / "prediction_distribution.svg")
    plt.close(fig)
    (reports / "alpha_report.md").write_text("# Alpha Factory Report\n\n```json\n" + json.dumps(metrics, indent=2, sort_keys=True) + "\n```\n")
    (run_dir / "index.html").write_text("<html><body><h1>Alpha Factory Report</h1><p>See reports/alpha_report.md.</p></body></html>\n")
    return reports / "alpha_report.md"
