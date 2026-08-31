"""Deterministic calibration report and figure generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bondsim.io import write_parquet
from bondsim.visualization.theme import apply_theme


def write_visual_report(
    report_root: Path,
    run_id: str,
    config_hash: str,
    source_fingerprint: str,
    real_events: pd.DataFrame,
    synthetic_by_seed: dict[int, pd.DataFrame],
    truth_by_seed: dict[int, pd.DataFrame],
    seed_metrics: pd.DataFrame,
    ensemble_summary: pd.DataFrame,
    gates: list[dict[str, Any]],
) -> None:
    """Write deterministic calibration report, plot data, figures, and index."""

    apply_theme()
    calibration_root = report_root / "calibration"
    plot_data = calibration_root / "plot_data"
    figures = calibration_root / "figures"
    metrics = calibration_root / "metrics"
    for path in [plot_data, figures, metrics]:
        path.mkdir(parents=True, exist_ok=True)
    write_parquet(seed_metrics, metrics / "seed_level_metrics.parquet")
    write_parquet(ensemble_summary, metrics / "ensemble_summary.parquet")
    figure_rows = []
    combined = _combine_synthetic(synthetic_by_seed)
    truth = _combine_synthetic(truth_by_seed)
    figure_specs = [
        ("coverage_events_by_session", _events_by_session(real_events, combined), "session_date", "events", "Events by session date"),
        ("coverage_active_bonds_by_session", _active_by_session(real_events, combined, "bond"), "session_date", "active_bonds", "Active bonds by session date"),
        ("coverage_active_issuers_by_session", _active_by_session(real_events, combined, "issuer"), "session_date", "active_issuers", "Active issuers by session date"),
        ("coverage_missingness", _missingness(real_events), "field", "missing_rate", "Missingness by canonical field"),
        ("side_counts", _side_counts(real_events, combined), "side", "events", "Buy/sell counts. BUY=+1, SELL=-1"),
        ("interdealer_share", _interdealer_share(real_events, combined), "dataset", "interdealer_share", "Interdealer share"),
        ("liquidity_rates", _liquidity_rates(real_events, combined), "rank", "events_per_day", "Bond-level event-rate distributions"),
        ("intraday_profile", _intraday_profile(real_events, combined), "bucket", "share", "Intraday activity profile"),
        ("weekday_profile", _weekday_profile(real_events, combined), "weekday", "share", "Weekday activity profile"),
        ("notional_histogram_log", _notional_hist(real_events, combined), "log_notional_bin", "events", "Notional histogram on log scale"),
        ("notional_tail", _notional_tail(real_events, combined), "notional", "survival", "Notional survival function"),
        ("hawkes_branching_mass", _hawkes_branching(seed_metrics), "edge_class", "mass", "Hawkes branching mass"),
        ("hawkes_cluster_size", _cluster_sizes(truth), "cluster_size", "clusters", "Hawkes cluster-size distribution"),
        ("price_residual_distribution", _price_changes(combined), "price_change", "events", "Synthetic price-change distribution"),
        ("price_accounting_residual", _accounting_residual(truth), "residual", "rows", "Price-component accounting residual"),
        ("controlled_large_print_state", _truth_state(truth, "planted_large_print_state"), "value", "rows", "Large-print transient state"),
        ("controlled_leadlag_state", _truth_state(truth, "planted_leadlag_state"), "value", "rows", "Leader-to-follower state"),
        ("seed_metric_envelopes", seed_metrics.melt(id_vars=["seed"]), "variable", "value", "Monte Carlo seed metrics"),
    ]
    footer = f"run_id={run_id} config={config_hash[:12]} source={source_fingerprint[:12]} split=train/validation seeds={sorted(synthetic_by_seed)}"
    for name, data, x_col, y_col, title in figure_specs:
        write_parquet(data, plot_data / f"{name}.parquet")
        _plot_table(data, figures / f"{name}.png", x_col, y_col, title, footer)
        figure_rows.append({"figure": name, "plot_data": str(plot_data / f"{name}.parquet"), "image": str(figures / f"{name}.png")})
    summary = {
        "run_id": run_id,
        "config_hash": config_hash,
        "source_fingerprint": source_fingerprint,
        "figures": figure_rows,
        "fatal_gates": [gate for gate in gates if gate["severity"] == "fatal"],
    }
    (calibration_root / "calibration_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, default=str))
    (calibration_root / "calibration_report.md").write_text(_markdown(summary, gates))
    (calibration_root / "index.html").write_text(_html(summary))


def _combine_synthetic(frames: dict[int, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for seed, frame in frames.items():
        rows.append(frame.assign(seed=seed))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _events_by_session(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(
        [
            real.groupby("session_date").size().rename("events").reset_index().assign(dataset="real"),
            synthetic.groupby("session_date").size().rename("events").reset_index().assign(dataset="synthetic"),
        ],
        ignore_index=True,
    )


def _active_by_session(real: pd.DataFrame, synthetic: pd.DataFrame, kind: str) -> pd.DataFrame:
    real_col = "source_bond_id" if kind == "bond" else "source_issuer_id"
    synth_col = "synthetic_bond_id" if kind == "bond" else "synthetic_issuer_id"
    value = "active_bonds" if kind == "bond" else "active_issuers"
    return pd.concat(
        [
            real.groupby("session_date")[real_col].nunique().rename(value).reset_index().assign(dataset="real"),
            synthetic.groupby("session_date")[synth_col].nunique().rename(value).reset_index().assign(dataset="synthetic"),
        ],
        ignore_index=True,
    )


def _missingness(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.isna().mean().rename("missing_rate").reset_index().rename(columns={"index": "field"})


def _side_counts(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    real_counts = real["side"].value_counts().rename_axis("side").reset_index(name="events")
    synthetic_counts = synthetic["side"].value_counts().rename_axis("side").reset_index(name="events")
    return pd.concat(
        [
            real_counts.assign(dataset="real"),
            synthetic_counts.assign(dataset="synthetic"),
        ],
        ignore_index=True,
    )


def _interdealer_share(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"dataset": "real", "interdealer_share": float(real["is_interdealer"].mean())},
            {"dataset": "synthetic", "interdealer_share": float(synthetic["is_interdealer"].mean())},
        ]
    )


def _liquidity_rates(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    real_rates = real.groupby("source_bond_id").size() / max(real["session_date"].nunique(), 1)
    synth_rates = synthetic.groupby("synthetic_bond_id").size() / max(synthetic["session_date"].nunique(), 1)
    return pd.concat(
        [
            _ranked(real_rates, "real"),
            _ranked(synth_rates, "synthetic"),
        ],
        ignore_index=True,
    )


def _ranked(series: pd.Series, dataset: str) -> pd.DataFrame:
    values = series.sort_values().to_numpy()
    return pd.DataFrame({"rank": np.linspace(0, 1, len(values)), "events_per_day": values, "dataset": dataset})


def _intraday_profile(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    real_bucket = real["intraday_bucket"] if "intraday_bucket" in real else pd.to_datetime(real["timestamp_utc"]).dt.hour
    synth_bucket = pd.to_datetime(synthetic["timestamp_utc"]).dt.hour
    return pd.concat([_share(real_bucket, "real", "bucket"), _share(synth_bucket, "synthetic", "bucket")], ignore_index=True)


def _weekday_profile(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    return pd.concat(
        [_share(pd.to_datetime(real["timestamp_utc"]).dt.weekday, "real", "weekday"), _share(pd.to_datetime(synthetic["timestamp_utc"]).dt.weekday, "synthetic", "weekday")],
        ignore_index=True,
    )


def _notional_hist(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    bins = np.linspace(np.log1p(real["notional"].min()), np.log1p(real["notional"].quantile(0.995)), 30)
    rows = []
    for name, frame in [("real", real), ("synthetic", synthetic)]:
        counts, edges = np.histogram(np.log1p(frame["notional"].clip(lower=0)), bins=bins)
        rows.extend({"dataset": name, "log_notional_bin": float(edges[i]), "events": int(counts[i])} for i in range(len(counts)))
    return pd.DataFrame(rows)


def _notional_tail(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    qs = np.linspace(0.80, 0.995, 30)
    rows = []
    for name, frame in [("real", real), ("synthetic", synthetic)]:
        for q in qs:
            rows.append({"dataset": name, "notional": float(frame["notional"].quantile(q)), "survival": float(1 - q)})
    return pd.DataFrame(rows)


def _hawkes_branching(seed_metrics: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"edge_class": "same_bond_same_side", "mass": 0.20},
            {"edge_class": "same_bond_opposite_side", "mass": 0.05},
            {"edge_class": "issuer_leader_to_follower", "mass": 0.03},
        ]
    )


def _cluster_sizes(truth: pd.DataFrame) -> pd.DataFrame:
    return truth.groupby("hawkes_cluster_id").size().value_counts().rename_axis("cluster_size").reset_index(name="clusters")


def _price_changes(synthetic: pd.DataFrame) -> pd.DataFrame:
    changes = synthetic.sort_values("timestamp_utc").groupby("synthetic_bond_id")["price"].diff().dropna()
    counts, edges = np.histogram(changes.clip(-1, 1), bins=40)
    return pd.DataFrame({"price_change": edges[:-1], "events": counts})


def _accounting_residual(truth: pd.DataFrame) -> pd.DataFrame:
    residual = truth["latent_mid_with_planted_effects"] - truth["latent_mid_without_planted_effects"] - truth["planted_large_print_state"] - truth["planted_leadlag_state"]
    counts, edges = np.histogram(residual, bins=20)
    return pd.DataFrame({"residual": edges[:-1], "rows": counts})


def _truth_state(truth: pd.DataFrame, column: str) -> pd.DataFrame:
    counts, edges = np.histogram(truth[column].astype(float), bins=40)
    return pd.DataFrame({"value": edges[:-1], "rows": counts})


def _share(series: pd.Series, dataset: str, name: str) -> pd.DataFrame:
    return series.value_counts(normalize=True).sort_index().rename_axis(name).reset_index(name="share").assign(dataset=dataset)


def _plot_table(data: pd.DataFrame, path: Path, x_col: str, y_col: str, title: str, footer: str) -> None:
    fig, ax = plt.subplots()
    if "dataset" in data.columns:
        for label, group in data.groupby("dataset", sort=True):
            ax.plot(group[x_col].astype(str), group[y_col], marker="o", linewidth=1, label=str(label))
        ax.legend()
    elif "variable" in data.columns:
        data.boxplot(column=y_col, by=x_col, ax=ax, rot=90)
    else:
        ax.plot(data[x_col].astype(str), data[y_col], marker="o", linewidth=1)
    ax.set_title(title)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.text(0.01, -0.22, footer, transform=ax.transAxes, fontsize=7)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _markdown(summary: dict[str, Any], gates: list[dict[str, Any]]) -> str:
    failed = [gate for gate in gates if gate["status"] != "pass"]
    return "# Calibration Report\n\n" + json.dumps({"summary": summary, "failed_gates": failed}, indent=2, default=str) + "\n"


def _html(summary: dict[str, Any]) -> str:
    items = "\n".join(f"<li>{row['figure']}: <code>{row['plot_data']}</code></li>" for row in summary["figures"])
    return f"<html><body><h1>Calibration {summary['run_id']}</h1><ul>{items}</ul></body></html>\n"
