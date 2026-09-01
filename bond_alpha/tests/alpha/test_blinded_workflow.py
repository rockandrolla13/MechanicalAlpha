import json
from pathlib import Path

import pandas as pd

from bondalpha.config import AlphaFactoryConfig, AlphaModelConfig, AlphaPaths
from bondsim.alpha_workflow import run_blinded_workflow
from bondsim.config import load_config


def test_blinded_workflow_order_with_existing_gate4_run(tmp_path, monkeypatch):
    gate4_config = load_config("configs/gate4.yaml")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "bondsim.alpha_workflow.verify_gate4_preconditions",
        lambda config: {
            "gate3_decision": "PASS",
            "calibration_id": "calibration-v1.0.0",
            "frozen_source_fingerprint": "test",
            "frozen_resolved_config_hash": "test",
        },
    )
    gate3_public = _write_public_dataset(tmp_path / "gate3_public")
    gate4_public = _write_public_dataset(tmp_path / "gate4_public")
    gate4_run = _write_gate4_run(tmp_path, gate4_public)
    alpha_config = AlphaFactoryConfig(
        paths=AlphaPaths(gate3_public_root=gate3_public, run_root=tmp_path / "alpha_runs", frozen_root=tmp_path / "alpha_frozen"),
        model=AlphaModelConfig(horizons=["30m"], train_fraction=0.60, validation_fraction=0.20),
    )
    result = run_blinded_workflow(
        gate4_config,
        alpha_config,
        gate3_public_root=gate3_public,
        gate4_run_id="gate4-test",
    )
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["gate3_public_root"] == str(gate3_public)
    assert manifest["gate4_public_root"] == str(gate4_public)
    assert manifest["truth_unblinded"] is False
    assert (gate4_run / "GATE4_RELEASED_TO_ALPHA_SPEC").read_text().strip() == result.alpha_spec.name
    assert (result.blind_output / "BLIND_LOCKED").exists()


def _write_gate4_run(tmp_path: Path, public_root: Path) -> Path:
    run = Path("runs/gate4/gate4-test")
    run.mkdir(parents=True, exist_ok=True)
    manifest = {
        "gate4_run_id": "gate4-test",
        "calibration_id": "calibration-v1.0.0",
        "mode": "smoke",
        "public_root": str(public_root),
        "truth_root": str(tmp_path / "truth"),
        "report_root": str(tmp_path / "reports"),
        "run_root": str(run),
        "quarantined": True,
        "alpha_spec_released": False,
        "scenarios": [],
        "preflight": {
            "gate3_decision_path": "reports/gate3/GATE3_DECISION.json",
            "calibration_id": "calibration-v1.0.0",
            "frozen_path": "models/frozen/calibration-v1.0.0",
            "frozen_source_fingerprint": "test",
            "frozen_resolved_config_hash": "test",
            "checksum_failures": [],
            "software_environment": {},
        },
    }
    (run / "gate4_manifest.json").write_text(json.dumps(manifest))
    return run


def _write_public_dataset(root: Path) -> Path:
    scenario = root / "scenario=controlled_all"
    trade_path = scenario / "trades" / "year=2026" / "month=01"
    trade_path.mkdir(parents=True)
    rows = []
    for bond in range(3):
        for idx in range(30):
            rows.append(
                {
                    "event_id": f"{root.name}_{bond}_{idx}",
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
    pd.DataFrame({"synthetic_bond_id": ["B0", "B1", "B2"], "synthetic_issuer_id": ["I0", "I1", "I0"]}).to_parquet(
        scenario / "bonds.parquet", index=False
    )
    return root
