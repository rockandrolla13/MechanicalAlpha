from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bondalpha.blinded_gate4 import run_strict_blinded_gate4_evaluation
from bondalpha.cli import develop_alpha
from bondalpha.config import AlphaFactoryConfig, AlphaModelConfig, AlphaPaths
from bondalpha.freeze import freeze_alpha_spec
from bondsim.io import manifest_for_files


def test_strict_blinded_gate4_evaluation_writes_required_layout(tmp_path: Path) -> None:
    gate3 = _write_public_root(tmp_path / "gate3", rows_per_scenario=12)
    config = AlphaFactoryConfig(
        paths=AlphaPaths(gate3_public_root=gate3, run_root=tmp_path / "alpha_runs", frozen_root=tmp_path / "alpha_frozen"),
        model=AlphaModelConfig(horizons=["30m"], train_fraction=0.6, validation_fraction=0.2),
    )
    alpha_run = develop_alpha(config, gate3)
    alpha_spec = freeze_alpha_spec(alpha_run, tmp_path / "alpha_frozen")
    gate4 = _write_public_root(tmp_path / "gate4" / "gate4-test", rows_per_scenario=14)
    result = run_strict_blinded_gate4_evaluation(alpha_spec, gate4, output_root=tmp_path / "alpha_gate4")

    run_dir = tmp_path / "alpha_gate4" / result["alpha_gate4_run_id"]
    assert (run_dir / "public_data_manifest.json").exists()
    assert (run_dir / "alpha_spec_manifest.json").exists()
    assert (run_dir / "features").is_dir()
    assert (run_dir / "labels").is_dir()
    assert (run_dir / "predictions").is_dir()
    assert (run_dir / "coefficients").is_dir()
    assert (run_dir / "metrics").is_dir()
    assert (run_dir / "plot_data").is_dir()
    assert (run_dir / "figures").is_dir()
    assert (run_dir / "blinded_report.md").exists()
    assert (run_dir / "blinded_report.json").exists()
    assert (run_dir / "checksums.sha256").exists()
    assert (run_dir / "BLINDED_COMPLETE").exists()
    assert json.loads((run_dir / "blinded_report.json").read_text())["truth_accessed"] is False


def _write_public_root(root: Path, rows_per_scenario: int) -> Path:
    for scenario in [
        "calibrated_realism",
        "controlled_all",
        "controlled_null",
        "reversal_only",
        "sign_only",
        "leadlag_only",
    ]:
        scenario_root = root / f"scenario={scenario}"
        trade_dir = scenario_root / "trades" / "year=2026" / "month=01"
        trade_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for idx in range(rows_per_scenario):
            rows.append(
                {
                    "event_id": f"{scenario}-{idx}",
                    "timestamp_utc": pd.Timestamp("2026-01-01 09:30", tz="UTC") + pd.Timedelta(minutes=30 * idx),
                    "session_date": str((pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx // 4)).date()),
                    "synthetic_bond_id": f"B{idx % 2}",
                    "synthetic_issuer_id": "I1",
                    "side": 1 if idx % 2 == 0 else -1,
                    "notional": 100000.0 + idx,
                    "price": 100.0 + ((-1) ** idx) * 0.01 * idx,
                    "is_interdealer": False,
                    "trade_type": "customer",
                    "venue_bucket": "synthetic",
                    "reporting_delay_ms": 0,
                    "currency": "USD",
                }
            )
        trade_path = trade_dir / "part-0000.parquet"
        bond_path = scenario_root / "bonds.parquet"
        pd.DataFrame(rows).to_parquet(trade_path, index=False)
        pd.DataFrame(
            [
                {"synthetic_bond_id": "B0", "synthetic_issuer_id": "I1"},
                {"synthetic_bond_id": "B1", "synthetic_issuer_id": "I1"},
            ]
        ).to_parquet(bond_path, index=False)
        manifest = manifest_for_files(
            [trade_path, bond_path],
            {
                "scenario": scenario,
                "rows": {"public": rows_per_scenario, "bonds": 2},
                "partitions": {"public": [{"path": str(trade_path), "rows": rows_per_scenario}]},
            },
        )
        (scenario_root / "manifest.json").write_text(json.dumps(manifest))
    return root
