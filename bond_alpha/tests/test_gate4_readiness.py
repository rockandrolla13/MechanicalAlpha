import json
from pathlib import Path

from bondsim.config import load_config
from bondsim.gate4_readiness import audit_public_truth_separation, run_gate4_readiness_audit


def test_gate4_readiness_audit_writes_required_files():
    config = load_config("configs/gate4.yaml")
    result = run_gate4_readiness_audit(config)
    assert result["gate3_decision_found"] is True
    assert result["approved_for_gate4"] is True
    assert result["frozen_calibration_found"] is True
    assert result["checksums_valid"] is True
    assert result["public_truth_separation_valid"] is True
    assert result["gate3_public_data_available"] is True
    assert result["gate4_ready"] is True
    saved = json.loads((config.paths.report_root / "gate4" / "readiness_audit.json").read_text())
    assert saved["gate4_ready"] is True


def test_gate4_schema_failure_is_reported_not_raised(tmp_path):
    public_root = tmp_path / "public" / "scenario=controlled_all"
    truth_root = tmp_path / "truth" / "scenario=controlled_all"
    public_part = public_root / "trades/year=2026/month=01/part-0000.parquet"
    truth_part = truth_root / "event_truth/year=2026/month=01/part-0000.parquet"
    public_part.parent.mkdir(parents=True)
    truth_part.parent.mkdir(parents=True)
    public_part.write_text("not a parquet file")
    truth_part.write_text("not a parquet file either")

    result = audit_public_truth_separation([Path(public_root)], [Path(truth_root)])

    assert result["public_truth_separation_valid"] is False
    assert any("parquet schema read failed" in failure for failure in result["failures"])
