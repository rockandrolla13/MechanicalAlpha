import json
from pathlib import Path

import pandas as pd

from bondsim.config import load_config
from bondsim.gate4_generation import GATE4_PRODUCTION_SCENARIOS, run_gate4_production_generation
from bondsim.pipeline import SimulationManifest
from bondsim.utils.hashing import file_sha256


def test_gate4_production_generation_writes_quarantined_complete_run(tmp_path, monkeypatch):
    config = load_config("configs/gate4_production.yaml")
    config.paths.processed_root = tmp_path / "processed"
    config.paths.model_root = tmp_path / "models"
    config.paths.synthetic_root = tmp_path / "synthetic"
    config.paths.truth_root = tmp_path / "synthetic_truth"
    config.paths.report_root = tmp_path / "reports"
    config.frozen_calibration_id = "calibration-test"

    gate3_root = config.paths.report_root / "gate3"
    gate3_root.mkdir(parents=True, exist_ok=True)
    (gate3_root / "GATE3_DECISION.json").write_text(
        json.dumps({"approved_for_gate4": True, "decision": "approve", "calibration_id": "calibration-test"})
    )
    _write_frozen_bundle(config.paths.model_root / "frozen" / "calibration-test", "calibration-test")

    class FakePipeline:
        def __init__(self, cfg):
            self.cfg = cfg

        def run(self, mode="full", scenario=None, force=False):
            scenario_name = scenario or self.cfg.scenario
            run_id = self.cfg.paths.synthetic_root.name
            state = json.loads((Path("runs/gate4") / run_id / "gate4_manifest.json").read_text())
            assert state["state"] == "RUNNING"
            public_root = self.cfg.paths.synthetic_root / f"scenario={scenario_name}"
            truth_root = self.cfg.paths.truth_root / f"scenario={scenario_name}"
            public_path = public_root / "trades" / "year=2026" / "month=08" / "part-0000.parquet"
            truth_path = truth_root / "event_truth" / "year=2026" / "month=08" / "part-0000.parquet"
            bonds_path = public_root / "bonds.parquet"
            public_path.parent.mkdir(parents=True, exist_ok=True)
            truth_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "event_id": f"{scenario_name}-event-1",
                        "timestamp_utc": pd.Timestamp("2026-08-31T09:30:00Z"),
                        "session_date": "2026-08-31",
                        "synthetic_bond_id": "bond-1",
                        "synthetic_issuer_id": "issuer-1",
                        "side": 1,
                        "price": 100.25,
                        "notional": 1_000_000.0,
                        "is_interdealer": False,
                        "scenario": scenario_name,
                    }
                ]
            ).to_parquet(public_path, index=False)
            pd.DataFrame(
                [
                    {
                        "event_id": f"{scenario_name}-event-1",
                        "timestamp_utc": pd.Timestamp("2026-08-31T09:30:00Z"),
                        "session_date": "2026-08-31",
                        "scenario": scenario_name,
                        "hawkes_cluster_id": "cluster-1",
                        "hawkes_parent_event_id": None,
                        "hawkes_generation": 0,
                        "hawkes_edge_class": "immigrant",
                        "is_immigrant": True,
                        "planted_large_print_state": 0.0,
                    }
                ]
            ).to_parquet(truth_path, index=False)
            pd.DataFrame([{"synthetic_bond_id": "bond-1", "synthetic_issuer_id": "issuer-1"}]).to_parquet(bonds_path, index=False)
            manifest = {
                "scenario": scenario_name,
                "mode": mode,
                "rows": {"public": 1, "truth": 1, "bonds": 1},
                "partitions": {
                    "public": [{"year": 2026, "month": 8, "path": str(public_path), "rows": 1}],
                    "truth": [{"year": 2026, "month": 8, "path": str(truth_path), "rows": 1}],
                },
                "liquidity": {"median": 2.0, "p10": 0.4, "max": 2.0},
            }
            manifest_path = public_root / "manifest.json"
            truth_manifest_path = truth_root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            truth_manifest_path.write_text(json.dumps(manifest))
            return SimulationManifest(
                scenario=scenario_name,
                mode=mode,
                public_path=public_path,
                truth_path=truth_path,
                manifest_path=manifest_path,
                validation={"passed": True, "failures": [], "public_rows": 1, "truth_rows": 1, "bond_rows": 1},
            )

    monkeypatch.setattr("bondsim.gate4_generation.SimulationPipeline", FakePipeline)

    result = run_gate4_production_generation(config, force=True)

    run_root = Path(result["run_root"])
    report_root = Path(result["report_root"])
    assert result["state"] == "COMPLETE"
    assert result["quarantined"] is True
    assert result["alpha_evaluation_run"] is False
    assert len(result["scenarios"]) == len(GATE4_PRODUCTION_SCENARIOS)
    assert (run_root / "GATE4_QUARANTINED").exists()
    assert (run_root / "GATE4_COMPLETE").exists()

    saved = json.loads((run_root / "gate4_manifest.json").read_text())
    assert saved["state"] == "COMPLETE"

    hashes = json.loads((run_root / "metrics" / "canonical_content_hashes.json").read_text())
    assert len(hashes["scenarios"]) == len(GATE4_PRODUCTION_SCENARIOS)
    assert hashes["canonical_public_root_sha256"]
    assert hashes["canonical_truth_root_sha256"]
    assert hashes["scenarios"][0]["public"]["canonical_content_sha256"]
    assert hashes["scenarios"][0]["truth"]["canonical_content_sha256"]

    structural = json.loads((run_root / "metrics" / "structural_validation.json").read_text())
    liquidity = json.loads((run_root / "metrics" / "liquidity_validation.json").read_text())
    assert structural["all_passed"] is True
    assert liquidity["all_passed"] is True
    assert all(row["passed"] for row in structural["scenarios"])
    assert all(row["passed"] for row in liquidity["scenarios"])

    reference = json.loads((run_root / "frozen_calibration_reference.json").read_text())
    assert reference["calibration_id"] == "calibration-test"
    assert reference["checksum_failures"] == []
    assert (report_root / "summary.json").exists()


def _write_frozen_bundle(root: Path, calibration_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "FROZEN").write_text(calibration_id)
    (root / "calibration_manifest.json").write_text(json.dumps({"resolved_config_hash": "cfg-1"}))
    (root / "source_fingerprint.json").write_text(json.dumps({"fingerprint": "src-1"}))
    (root / "selected_models.json").write_text(json.dumps({"selected": "empirical_fallback"}))
    (root / "software_environment.json").write_text(json.dumps({"python": "3.12", "operating_system": "linux", "cpu_architecture": "x86_64", "package_versions": {}}))
    (root / "resolved_config.yaml").write_text("scenario: calibrated_realism\n")
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")
