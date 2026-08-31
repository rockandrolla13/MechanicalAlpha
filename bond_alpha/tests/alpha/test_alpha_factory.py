import json
from pathlib import Path

import pandas as pd

from bondalpha.cli import develop_alpha, evaluate_blind
from bondalpha.config import AlphaFactoryConfig, AlphaModelConfig, AlphaPaths
from bondalpha.freeze import freeze_alpha_spec


def test_alpha_develop_freeze_and_blind_evaluate(tmp_path):
    public_root = _write_public_dataset(tmp_path / "public")
    config = AlphaFactoryConfig(
        paths=AlphaPaths(gate3_public_root=public_root, run_root=tmp_path / "runs", frozen_root=tmp_path / "frozen"),
        model=AlphaModelConfig(horizons=["30m"], train_fraction=0.60, validation_fraction=0.20),
    )
    run = develop_alpha(config, public_root)
    frozen = freeze_alpha_spec(run, tmp_path / "frozen")
    blind = tmp_path / "blind"
    result = evaluate_blind(frozen, public_root, blind)
    assert result["locked"] is True
    assert (blind / "BLIND_LOCKED").exists()
    assert (blind / "predictions.parquet").exists()
    assert json.loads((blind / "BLIND_EVALUATION.json").read_text())["rows"] > 0


def _write_public_dataset(root: Path) -> Path:
    scenario = root / "scenario=controlled_all"
    trade_path = scenario / "trades" / "year=2026" / "month=01"
    trade_path.mkdir(parents=True)
    rows = []
    for bond in range(3):
        for idx in range(30):
            rows.append(
                {
                    "event_id": f"e{bond}_{idx}",
                    "timestamp_utc": pd.Timestamp("2026-01-01 09:30") + pd.Timedelta(minutes=idx * 30),
                    "session_date": str((pd.Timestamp("2026-01-01") + pd.Timedelta(days=idx // 8)).date()),
                    "synthetic_bond_id": f"B{bond}",
                    "synthetic_issuer_id": f"I{bond % 2}",
                    "side": 1 if idx % 2 == 0 else -1,
                    "notional": 100000 + idx * 1000 + bond * 500,
                    "price": 100 + bond * 0.1 + idx * 0.01 * (1 if bond != 1 else -1),
                    "is_interdealer": idx % 7 == 0,
                    "trade_type": "customer",
                    "venue_bucket": "synthetic",
                    "reporting_delay_ms": 0,
                    "currency": "USD",
                }
            )
    pd.DataFrame(rows).to_parquet(trade_path / "part-0000.parquet", index=False)
    pd.DataFrame(
        {
            "synthetic_bond_id": ["B0", "B1", "B2"],
            "synthetic_issuer_id": ["I0", "I1", "I0"],
            "currency": ["USD", "USD", "USD"],
        }
    ).to_parquet(scenario / "bonds.parquet", index=False)
    return root
