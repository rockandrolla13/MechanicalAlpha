from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from bondalpha.cli import main


def test_public_alpha_cli_aliases(tmp_path: Path) -> None:
    public_root = _public_dataset(tmp_path / "public")
    config = tmp_path / "alpha.yaml"
    config.write_text(
        "project: alpha_factory_v1\n"
        "paths:\n"
        f"  gate3_public_root: {public_root}\n"
        f"  run_root: {tmp_path / 'runs'}\n"
        f"  frozen_root: {tmp_path / 'frozen'}\n"
        f"  report_root: {tmp_path / 'reports'}\n"
        "model:\n"
        "  horizons: [30m]\n"
        "  train_fraction: 0.6\n"
        "  validation_fraction: 0.2\n"
    )

    assert main(["inspect", "--public-root", str(public_root)]) == 0
    assert main(["build-features", "--public-root", str(public_root), "--config", str(config)]) == 0
    assert main(["research", "--public-root", str(public_root), "--config", str(config)]) == 0
    assert main(["validate", "--public-root", str(public_root), "--config", str(config)]) == 0

    assert (tmp_path / "reports" / "gate3" / "data_audit.md").exists()
    assert (tmp_path / "reports" / "gate3" / "alpha_selection.json").exists()
    payload = json.loads((tmp_path / "reports" / "gate3" / "alpha_selection.json").read_text())
    assert "approved_families" in payload


def _public_dataset(root: Path) -> Path:
    trade_root = root / "scenario=controlled_all" / "trades" / "year=2026" / "month=01"
    trade_root.mkdir(parents=True)
    rows = []
    for idx in range(12):
        rows.append(
            {
                "event_id": f"e{idx}",
                "timestamp_utc": pd.Timestamp("2026-01-01 09:30", tz="UTC") + pd.Timedelta(minutes=30 * idx),
                "session_date": str((pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx // 4)).date()),
                "synthetic_bond_id": "B1",
                "synthetic_issuer_id": "I1",
                "side": 1 if idx % 2 == 0 else -1,
                "notional": 100000.0 + idx,
                "price": 100.0 + 0.01 * idx,
                "is_interdealer": False,
                "trade_type": "customer",
                "venue_bucket": "synthetic",
                "reporting_delay_ms": 0,
                "currency": "USD",
            }
        )
    pd.DataFrame(rows).to_parquet(trade_root / "part-0000.parquet", index=False)
    pd.DataFrame([{"synthetic_bond_id": "B1", "synthetic_issuer_id": "I1"}]).to_parquet(root / "scenario=controlled_all" / "bonds.parquet")
    return root
