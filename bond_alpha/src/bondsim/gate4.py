"""Gate 4 quarantined full-generation orchestration."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from bondsim.calibration.frozen import current_software_environment, load_frozen_calibration
from bondsim.config import BondSimConfig
from bondsim.io import write_json
from bondsim.utils.hashing import file_sha256
from bondsim.pipeline import SimulationPipeline
from bondsim.utils.hashing import stable_json_hash


GATE4_SCENARIOS = [
    "calibrated_realism",
    "controlled_all",
    "controlled_null",
    "reversal_only",
    "sign_only",
    "leadlag_only",
]


def run_gate4(config: BondSimConfig, *, mode: str = "full", force: bool = False) -> dict[str, Any]:
    """Run Gate 4 into quarantined public and truth roots."""

    preflight = verify_gate4_preconditions(config)
    run_id = gate4_run_id(config, preflight, mode)
    public_root = Path("data/synthetic/gate4") / run_id
    truth_root = Path("data/synthetic_truth/gate4") / run_id
    report_root = Path("reports/gate4") / run_id
    run_root = Path("runs/gate4") / run_id
    if (run_root / "GATE4_QUARANTINED").exists() and not force:
        raise FileExistsError(f"Gate 4 run already exists: {run_root}. Use --force.")
    run_root.mkdir(parents=True, exist_ok=True)
    for child in ["progress", "metrics", "logs"]:
        (run_root / child).mkdir(parents=True, exist_ok=True)
    report_root.mkdir(parents=True, exist_ok=True)
    _write_preflight_artifacts(config, preflight, run_root)
    manifests: list[dict[str, Any]] = []
    for scenario in GATE4_SCENARIOS:
        scenario_config = copy.deepcopy(config)
        scenario_config.scenario = scenario
        scenario_config.paths.synthetic_root = public_root
        scenario_config.paths.truth_root = truth_root
        scenario_config.paths.report_root = report_root / scenario
        result = SimulationPipeline(scenario_config).run(mode=mode, scenario=scenario, force=force)
        manifest = json.loads(result.manifest_path.read_text())
        manifest["gate4_run_id"] = run_id
        manifest["gate4_quarantined"] = True
        manifest["frozen_calibration_id"] = preflight["calibration_id"]
        manifest["frozen_calibration_path"] = preflight["frozen_path"]
        write_json(manifest, result.manifest_path)
        truth_manifest = truth_root / f"scenario={scenario}" / "manifest.json"
        if truth_manifest.exists():
            payload = json.loads(truth_manifest.read_text())
            payload.update(
                {
                    "gate4_run_id": run_id,
                    "gate4_quarantined": True,
                    "frozen_calibration_id": preflight["calibration_id"],
                    "frozen_calibration_path": preflight["frozen_path"],
                }
            )
            write_json(payload, truth_manifest)
        manifests.append({"scenario": scenario, "manifest_path": str(result.manifest_path), "rows": manifest.get("rows", {})})
    decision = {
        "gate4_run_id": run_id,
        "calibration_id": preflight["calibration_id"],
        "mode": mode,
        "public_root": str(public_root),
        "truth_root": str(truth_root),
        "report_root": str(report_root),
        "run_root": str(run_root),
        "quarantined": True,
        "alpha_spec_released": False,
        "scenarios": manifests,
        "preflight": preflight,
    }
    write_json(decision, run_root / "gate4_manifest.json")
    write_json(decision, run_root / "run_manifest.json")
    write_json(decision, report_root / "gate4_manifest.json")
    write_json(decision, report_root / "summary.json")
    (run_root / "GATE4_QUARANTINED").write_text(
        "Gate 4 public output is quarantined until an alpha specification is frozen.\n"
    )
    (report_root / "summary.md").write_text(_summary_markdown(decision))
    (report_root / "index.html").write_text(
        f"<html><body><h1>Gate 4 {run_id}</h1><p>Quarantined: true</p><p>Calibration: {preflight['calibration_id']}</p></body></html>\n"
    )
    _write_checksums(run_root)
    return decision


def verify_gate4_preconditions(config: BondSimConfig) -> dict[str, Any]:
    """Verify Gate 3 approval and frozen calibration integrity."""

    decision_path = config.paths.report_root / "gate3" / "GATE3_DECISION.json"
    if not decision_path.exists():
        raise FileNotFoundError(f"Gate 3 decision not found: {decision_path}")
    gate3 = json.loads(decision_path.read_text())
    if not gate3.get("approved_for_gate4"):
        raise RuntimeError(f"Gate 3 is not approved for Gate 4: {gate3.get('decision')}")
    calibration_id = config.frozen_calibration_id or gate3.get("calibration_id")
    if not calibration_id:
        raise RuntimeError("Gate 4 requires frozen_calibration_id or a Gate 3 calibration_id")
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


def gate4_run_id(config: BondSimConfig, preflight: dict[str, Any], mode: str) -> str:
    """Create a deterministic Gate 4 run identifier."""

    payload = {
        "gate": "gate4",
        "calibration_id": preflight["calibration_id"],
        "source_fingerprint": preflight["frozen_source_fingerprint"],
        "resolved_config_hash": preflight["frozen_resolved_config_hash"],
        "mode": mode,
        "master_seed": config.project.master_seed,
        "n_bonds": config.universe.n_bonds,
        "n_sessions": config.simulation.n_sessions,
        "scenarios": GATE4_SCENARIOS,
    }
    return "gate4-" + stable_json_hash(payload)[:16]


def release_gate4_public(run_root: Path, alpha_spec_id: str) -> dict[str, Any]:
    """Mark a quarantined Gate 4 run as released to a frozen alpha spec."""

    manifest_path = run_root / "gate4_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Gate 4 manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    manifest["alpha_spec_released"] = True
    manifest["released_to_alpha_spec_id"] = alpha_spec_id
    write_json(manifest, manifest_path)
    (run_root / "GATE4_RELEASED_TO_ALPHA_SPEC").write_text(alpha_spec_id + "\n")
    _write_checksums(run_root)
    return manifest


def finalize_gate4_run(run_root: Path) -> dict[str, Any]:
    """Backfill checksums and compatibility files for an existing Gate 4 run."""

    manifest_path = run_root / "gate4_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Gate 4 manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text())
    write_json(manifest, run_root / "run_manifest.json")
    preflight = manifest.get("preflight", {})
    if preflight:
        gate3_path = Path(str(preflight.get("gate3_decision_path", "")))
        if gate3_path.exists():
            write_json(json.loads(gate3_path.read_text()), run_root / "gate3_decision.json")
        frozen_path = Path(str(preflight.get("frozen_path", "")))
        resolved = frozen_path / "resolved_config.yaml"
        if resolved.exists():
            (run_root / "resolved_config.yaml").write_text(resolved.read_text())
        source = frozen_path / "source_fingerprint.json"
        if source.exists():
            write_json(json.loads(source.read_text()), run_root / "source_fingerprint.json")
        write_json(
            {
                "calibration_id": preflight.get("calibration_id"),
                "path": preflight.get("frozen_path"),
                "source_fingerprint": preflight.get("frozen_source_fingerprint"),
                "resolved_config_hash": preflight.get("frozen_resolved_config_hash"),
                "checksum_failures": preflight.get("checksum_failures", []),
            },
            run_root / "frozen_calibration_reference.json",
        )
        write_json(preflight.get("software_environment", {}), run_root / "software_environment.json")
        write_json({"master_seed": manifest.get("preflight", {}).get("software_environment", {}).get("master_seed", "see resolved_config.yaml")}, run_root / "seed_manifest.json")
    for child in ["progress", "metrics", "logs"]:
        (run_root / child).mkdir(parents=True, exist_ok=True)
    _write_checksums(run_root)
    report_root = Path(manifest["report_root"])
    report_root.mkdir(parents=True, exist_ok=True)
    write_json(manifest, report_root / "summary.json")
    (report_root / "summary.md").write_text(_summary_markdown(manifest))
    (report_root / "index.html").write_text(
        f"<html><body><h1>Gate 4 {manifest['gate4_run_id']}</h1><p>Quarantined: {manifest['quarantined']}</p></body></html>\n"
    )
    return manifest


def _summary_markdown(decision: dict[str, Any]) -> str:
    rows = "\n".join(
        f"- {item['scenario']}: {item.get('rows', {})}" for item in decision["scenarios"]
    )
    return (
        "# Gate 4 Quarantined Run\n\n"
        f"- run_id: `{decision['gate4_run_id']}`\n"
        f"- calibration_id: `{decision['calibration_id']}`\n"
        f"- public_root: `{decision['public_root']}`\n"
        f"- truth_root: `{decision['truth_root']}`\n"
        f"- quarantined: `{decision['quarantined']}`\n\n"
        "## Scenario Rows\n\n"
        f"{rows}\n"
    )


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


def _write_checksums(root: Path) -> None:
    rows = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "checksums.sha256"):
        rows.append(f"{file_sha256(path)}  {path.relative_to(root)}")
    (root / "checksums.sha256").write_text("\n".join(rows) + "\n")
