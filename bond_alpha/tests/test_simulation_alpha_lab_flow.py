from __future__ import annotations

import pandas as pd

from mechanical_alpha.analysis import summarize_signals_by_alpha
from mechanical_alpha.lab import discover_synthetic_scenarios, load_synthetic_scenario, run_standalone_alphas


def test_lab_discovers_loads_runs_and_summarizes_standalone_alphas(tmp_path) -> None:
    data_root = tmp_path / "synthetic"
    scenario_root = data_root / "scenario=controlled_all"
    output = tmp_path / "signals.parquet"
    _write_synthetic_root(scenario_root)

    scenarios = discover_synthetic_scenarios(data_root)
    bundle = load_synthetic_scenario(scenario_root)
    run = run_standalone_alphas(scenario_root, ["A1", "A2"], output_path=output)
    repeated_summary = summarize_signals_by_alpha(run.signals)

    assert scenarios["scenario"].tolist() == ["controlled_all"]
    assert len(bundle.events) == 8
    assert output.exists()
    assert run.alpha_ids == ("A1", "A2")
    assert run.summary.equals(repeated_summary)
    assert run.summary["alpha_id"].tolist() == ["A1", "A2"]
    assert run.summary["rows"].tolist() == [8, 8]
    assert run.summary["bonds"].tolist() == [2, 2]
    assert (run.summary["signal_columns"] > 0).all()
    assert (run.summary["finite_signal_values"] > 0).all()
    assert run.hooks == {
        "signals_rows": 16,
        "summary_rows": 2,
        "required_next_modules": ("portfolio", "pnl_metrics"),
        "status": "not_invoked",
    }


def test_signal_summary_is_deterministic_for_empty_input() -> None:
    summary = summarize_signals_by_alpha(pd.DataFrame(columns=["alpha_id"]))

    assert summary.empty
    assert summary.columns.tolist() == [
        "alpha_id",
        "rows",
        "bonds",
        "signal_columns",
        "finite_signal_values",
        "mean_abs_signal",
        "first_prediction_timestamp",
        "last_prediction_timestamp",
    ]


def _write_synthetic_root(root: object) -> None:
    path = pd.io.common.stringify_path(root)
    from pathlib import Path

    root_path = Path(path)
    trade_root = root_path / "trades/year=2026/month=01"
    trade_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "synthetic_bond_id": ["b1", "b2"],
            "synthetic_issuer_id": ["iss1", "iss1"],
            "liquidity_bucket": ["liquid", "illiquid"],
            "rating_bucket": ["BBB", "BBB"],
            "sector": ["industrial", "industrial"],
            "maturity_bucket": ["5y", "10y"],
            "dv01": [10.0, 20.0],
            "cr01": [15.0, 25.0],
        }
    ).to_parquet(root_path / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": [f"e{i}" for i in range(8)],
            "timestamp_utc": pd.date_range("2026-01-02 09:00", periods=8, freq="30min", tz="UTC"),
            "session_date": ["2026-01-02"] * 8,
            "synthetic_bond_id": ["b1"] * 5 + ["b2"] * 3,
            "synthetic_issuer_id": ["iss1"] * 8,
            "side": [1, -1] * 4,
            "notional": [100.0 + idx for idx in range(8)],
            "price": [100.0] * 8,
            "is_interdealer": [False] * 8,
            "dv01": [1.0 + idx for idx in range(8)],
            "cr01": [2.0 + idx for idx in range(8)],
        }
    ).to_parquet(trade_root / "part-0000.parquet", index=False)
