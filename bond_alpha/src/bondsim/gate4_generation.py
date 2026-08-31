"""Gate 4 production-generation core with quarantined outputs and run-state artifacts."""

from __future__ import annotations

import copy
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from bondsim.calibration.frozen import current_software_environment, load_frozen_calibration
from bondsim.calibration.metrics import parquet_hashes
from bondsim.config import BondSimConfig
from bondsim.io import write_json
from bondsim.pipeline import SimulationPipeline
from bondsim.utils.hashing import file_sha256, stable_json_hash


GATE4_PRODUCTION_SCENARIOS = [
    "calibrated_realism",
    "controlled_all",
    "controlled_null",
    "reversal_only",
    "sign_only",
    "leadlag_only",
]


def run_gate4_production_generation(config: BondSimConfig, *, mode: str = "full", force: bool = False) -> dict[str, Any]:
    """Run Gate 4 production generation into quarantined public and truth roots."""

    preflight = verify_gate4_production_preconditions(config)
    run_id = gate4_production_run_id(config, preflight, mode)
    public_root = Path("data/quarantine/gate4_public") / run_id
    truth_root = Path("data/quarantine/gate4_truth") / run_id
    report_root = Path("reports/gate4") / run_id
    run_root = Path("runs/gate4") / run_id
    if force:
        for path in (public_root, truth_root, report_root, run_root):
            shutil.rmtree(path, ignore_errors=True)
    if run_root.exists() and (run_root / "gate4_manifest.json").exists() and not force:
        raise FileExistsError(f"Gate 4 production run already exists: {run_root}. Use --force.")

    for child in ("progress", "metrics", "logs"):
        (run_root / child).mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    public_root.mkdir(parents=True, exist_ok=True)
    truth_root.mkdir(parents=True, exist_ok=True)

    decision = {
        "gate4_run_id": run_id,
        "state": "RUNNING",
        "started_at_utc": _now_utc(),
        "completed_at_utc": None,
        "calibration_id": preflight["calibration_id"],
        "mode": mode,
        "public_root": str(public_root),
        "truth_root": str(truth_root),
        "report_root": str(report_root),
        "run_root": str(run_root),
        "quarantined": True,
        "alpha_spec_released": False,
        "alpha_evaluation_run": False,
        "scenarios": [],
        "preflight": preflight,
    }
    _write_preflight_artifacts(config, preflight, run_root)
    _write_run_state(decision, run_root, report_root)
    (run_root / "RUNNING").write_text(_now_utc() + "\n")
    (run_root / "GATE4_QUARANTINED").write_text(
        "Gate 4 production outputs are quarantined until a frozen alpha specification is attached.\n"
    )

    scenario_hashes: list[dict[str, Any]] = []
    structural_rows: list[dict[str, Any]] = []
    liquidity_rows: list[dict[str, Any]] = []

    for scenario in GATE4_PRODUCTION_SCENARIOS:
        scenario_config = copy.deepcopy(config)
        scenario_config.scenario = scenario
        scenario_config.paths.synthetic_root = public_root
        scenario_config.paths.truth_root = truth_root
        scenario_config.paths.report_root = report_root / scenario
        result = SimulationPipeline(scenario_config).run(mode=mode, scenario=scenario, force=force)
        public_manifest = json.loads(result.manifest_path.read_text())
        truth_manifest_path = truth_root / f"scenario={scenario}" / "manifest.json"
        truth_manifest = json.loads(truth_manifest_path.read_text()) if truth_manifest_path.exists() else {}
        public_manifest.update(_gate4_manifest_fields(run_id, preflight))
        truth_manifest.update(_gate4_manifest_fields(run_id, preflight))
        write_json(public_manifest, result.manifest_path)
        if truth_manifest_path.exists():
            write_json(truth_manifest, truth_manifest_path)

        scenario_record = {
            "scenario": scenario,
            "manifest_path": str(result.manifest_path),
            "truth_manifest_path": str(truth_manifest_path),
            "rows": public_manifest.get("rows", {}),
            "validation": result.validation,
        }
        decision["scenarios"].append(scenario_record)
        scenario_hashes.append(_scenario_content_hashes(scenario, public_manifest, truth_manifest_path.parent))
        structural_rows.append(_structural_validation_row(scenario, result.validation, public_manifest))
        liquidity_rows.append(_liquidity_validation_row(scenario, public_manifest, config))
        _write_run_state(decision, run_root, report_root)

    content_hashes = {
        "run_id": run_id,
        "public_root": str(public_root),
        "truth_root": str(truth_root),
        "scenarios": scenario_hashes,
        "canonical_public_root_sha256": stable_json_hash(
            [{"scenario": row["scenario"], "public_root_sha256": row["public_root_sha256"]} for row in scenario_hashes]
        ),
        "canonical_truth_root_sha256": stable_json_hash(
            [{"scenario": row["scenario"], "truth_root_sha256": row["truth_root_sha256"]} for row in scenario_hashes]
        ),
    }
    structural_validation = {
        "run_id": run_id,
        "all_passed": all(row["passed"] for row in structural_rows),
        "scenarios": structural_rows,
    }
    liquidity_validation = {
        "run_id": run_id,
        "all_passed": all(row["passed"] for row in liquidity_rows),
        "targets": {
            "median_events_per_day_range": list(config.validation.liquidity_median_range),
            "p10_events_per_day_range": list(config.validation.liquidity_p10_range),
        },
        "scenarios": liquidity_rows,
    }

    write_json(content_hashes, run_root / "metrics" / "canonical_content_hashes.json")
    write_json(structural_validation, run_root / "metrics" / "structural_validation.json")
    write_json(liquidity_validation, run_root / "metrics" / "liquidity_validation.json")
    write_json(structural_validation, run_root / "structural_validation.json")
    write_json(liquidity_validation, run_root / "liquidity_validation.json")
    write_json(content_hashes, report_root / "canonical_content_hashes.json")
    write_json(structural_validation, report_root / "structural_validation.json")
    write_json(liquidity_validation, report_root / "liquidity_validation.json")

    decision["state"] = "COMPLETE"
    decision["completed_at_utc"] = _now_utc()
    decision["artifacts"] = {
        "canonical_content_hashes": str(run_root / "metrics" / "canonical_content_hashes.json"),
        "structural_validation": str(run_root / "metrics" / "structural_validation.json"),
        "liquidity_validation": str(run_root / "metrics" / "liquidity_validation.json"),
    }
    _write_run_state(decision, run_root, report_root)
    write_json(decision, run_root / "generation_manifest.json")
    (run_root / "GATE4_COMPLETE").write_text(decision["completed_at_utc"] + "\n")
    (run_root / "RUNNING").replace(run_root / "COMPLETE")
    (report_root / "summary.md").write_text(_summary_markdown(decision))
    (report_root / "index.html").write_text(
        f"<html><body><h1>Gate 4 {run_id}</h1><p>State: COMPLETE</p><p>Quarantined: true</p></body></html>\n"
    )
    Path("reports/gate4").mkdir(parents=True, exist_ok=True)
    write_json(decision, Path("reports/gate4") / "generation_summary.json")
    (Path("reports/gate4") / "generation_summary.md").write_text(_summary_markdown(decision))
    _write_checksums(run_root)
    return decision


def verify_gate4_production_preconditions(config: BondSimConfig) -> dict[str, Any]:
    """Verify Gate 3 approval and frozen-calibration integrity before production generation."""

    decision_path = config.paths.report_root / "gate3" / "GATE3_DECISION.json"
    if not decision_path.exists():
        raise FileNotFoundError(f"Gate 3 decision not found: {decision_path}")
    gate3 = json.loads(decision_path.read_text())
    if not gate3.get("approved_for_gate4"):
        raise RuntimeError(f"Gate 3 is not approved for Gate 4: {gate3.get('decision')}")
    calibration_id = config.frozen_calibration_id or gate3.get("calibration_id")
    if not calibration_id:
        raise RuntimeError("Gate 4 production generation requires frozen_calibration_id or a Gate 3 calibration_id")
    frozen = load_frozen_calibration(str(calibration_id), config.paths.model_root)
    return {
        "gate3_decision_path": str(decision_path),
        "gate3_decision": gate3.get("decision"),
        "approved_for_gate4": bool(gate3.get("approved_for_gate4")),
        "calibration_id": frozen.calibration_id,
        "frozen_path": str(frozen.path),
        "frozen_source_fingerprint": frozen.source_fingerprint_hash,
        "frozen_resolved_config_hash": frozen.resolved_config_hash,
        "checksum_failures": frozen.checksum_failures,
        "environment_deviations": frozen.environment_deviations,
        "software_environment": current_software_environment(),
    }


def gate4_production_run_id(config: BondSimConfig, preflight: dict[str, Any], mode: str) -> str:
    """Create a deterministic Gate 4 production run identifier."""

    payload = {
        "gate": "gate4_production",
        "calibration_id": preflight["calibration_id"],
        "source_fingerprint": preflight["frozen_source_fingerprint"],
        "resolved_config_hash": preflight["frozen_resolved_config_hash"],
        "mode": mode,
        "master_seed": config.project.master_seed,
        "n_bonds": config.universe.n_bonds,
        "n_sessions": config.simulation.n_sessions,
        "scenarios": GATE4_PRODUCTION_SCENARIOS,
    }
    return "gate4-" + stable_json_hash(payload)[:16]


def _scenario_content_hashes(scenario: str, manifest: dict[str, Any], truth_root: Path) -> dict[str, Any]:
    public_paths = [Path(item["path"]) for item in manifest.get("partitions", {}).get("public", [])]
    truth_paths = [Path(item["path"]) for item in manifest.get("partitions", {}).get("truth", [])]
    bonds_path = Path(public_paths[0]).parents[3] / "bonds.parquet" if public_paths else Path()
    public_hash = parquet_hashes(public_paths, sort_columns=["event_id"])
    truth_hash = parquet_hashes(truth_paths, sort_columns=["event_id"])
    bonds_hash = parquet_hashes([bonds_path], sort_columns=["synthetic_bond_id"]) if bonds_path.exists() else None
    return {
        "scenario": scenario,
        "public": public_hash,
        "truth": truth_hash,
        "bonds": bonds_hash,
        "public_root_sha256": stable_json_hash({"public": public_hash, "bonds": bonds_hash}),
        "truth_root_sha256": stable_json_hash({"truth": truth_hash}),
    }


def _structural_validation_row(scenario: str, validation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "passed": bool(validation.get("passed")),
        "failures": list(validation.get("failures", [])),
        "public_rows": int(validation.get("public_rows", manifest.get("rows", {}).get("public", 0))),
        "truth_rows": int(validation.get("truth_rows", manifest.get("rows", {}).get("truth", 0))),
        "bond_rows": int(validation.get("bond_rows", manifest.get("rows", {}).get("bonds", 0))),
    }


def _liquidity_validation_row(scenario: str, manifest: dict[str, Any], config: BondSimConfig) -> dict[str, Any]:
    liquidity = manifest.get("liquidity", {})
    median = float(liquidity.get("median", 0.0))
    p10 = float(liquidity.get("p10", 0.0))
    median_range = config.validation.liquidity_median_range
    p10_range = config.validation.liquidity_p10_range
    median_ok = median_range[0] <= median <= median_range[1]
    p10_ok = p10_range[0] <= p10 <= p10_range[1]
    return {
        "scenario": scenario,
        "passed": bool(median_ok and p10_ok),
        "median_events_per_day": median,
        "p10_events_per_day": p10,
        "maximum_events_per_day": float(liquidity.get("max", 0.0)),
        "median_target_range": list(median_range),
        "p10_target_range": list(p10_range),
    }


def _gate4_manifest_fields(run_id: str, preflight: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate4_run_id": run_id,
        "gate4_quarantined": True,
        "frozen_calibration_id": preflight["calibration_id"],
        "frozen_calibration_path": preflight["frozen_path"],
    }


def _write_preflight_artifacts(config: BondSimConfig, preflight: dict[str, Any], run_root: Path) -> None:
    (run_root / "resolved_config.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
    gate3_path = Path(preflight["gate3_decision_path"])
    if gate3_path.exists():
        write_json(json.loads(gate3_path.read_text()), run_root / "gate3_decision.json")
    write_json(
        {
            "calibration_id": preflight["calibration_id"],
            "path": preflight["frozen_path"],
            "source_fingerprint": preflight["frozen_source_fingerprint"],
            "resolved_config_hash": preflight["frozen_resolved_config_hash"],
            "checksum_failures": preflight["checksum_failures"],
        },
        run_root / "frozen_calibration_reference.json",
    )
    write_json({"fingerprint": preflight["frozen_source_fingerprint"]}, run_root / "source_fingerprint.json")
    write_json(preflight["software_environment"], run_root / "software_environment.json")
    write_json({"master_seed": config.project.master_seed, "scenario_policy": "canonical_seed_for_all_scenarios"}, run_root / "seed_manifest.json")


def _write_run_state(decision: dict[str, Any], run_root: Path, report_root: Path) -> None:
    write_json(decision, run_root / "gate4_manifest.json")
    write_json(decision, run_root / "run_manifest.json")
    write_json(decision, run_root / "progress" / "state.json")
    write_json(decision, report_root / "gate4_manifest.json")
    write_json(decision, report_root / "summary.json")


def _summary_markdown(decision: dict[str, Any]) -> str:
    rows = "\n".join(f"- {item['scenario']}: {item.get('rows', {})}" for item in decision["scenarios"])
    return (
        "# Gate 4 Production Generation\n\n"
        f"- run_id: `{decision['gate4_run_id']}`\n"
        f"- state: `{decision['state']}`\n"
        f"- calibration_id: `{decision['calibration_id']}`\n"
        f"- public_root: `{decision['public_root']}`\n"
        f"- truth_root: `{decision['truth_root']}`\n"
        f"- quarantined: `{decision['quarantined']}`\n"
        f"- alpha_evaluation_run: `{decision['alpha_evaluation_run']}`\n\n"
        "## Scenario Rows\n\n"
        f"{rows}\n"
    )


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
