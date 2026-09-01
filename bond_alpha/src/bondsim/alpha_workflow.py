"""Executable blinded Gate 4 Alpha Factory workflow.

This bridge owns orchestration across simulator and alpha packages.
Formula code and alpha-only evaluation should not import this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bondalpha.config import AlphaFactoryConfig
from bondalpha.freeze import freeze_alpha_spec, verify_checksums
from bondsim.config import BondSimConfig
from bondsim.gate4 import finalize_gate4_run, release_gate4_public, run_gate4, verify_gate4_preconditions
from mechanical_alpha.hashing import file_sha256, stable_json_hash
from mechanical_alpha.io import write_json


@dataclass(frozen=True)
class BlindedWorkflowResult:
    """Paths produced by one locked blinded workflow run."""

    workflow_run_id: str
    workflow_root: Path
    gate4_run_id: str
    alpha_run: Path
    alpha_spec: Path
    blind_output: Path
    manifest_path: Path


def run_blinded_workflow(
    gate4_config: BondSimConfig,
    alpha_config: AlphaFactoryConfig,
    *,
    gate3_public_root: Path,
    gate4_run_id: str | None = None,
    gate4_mode: str = "full",
    force: bool = False,
) -> BlindedWorkflowResult:
    """Verify, quarantine, develop, freeze, release, and run one blind evaluation."""

    preflight = verify_gate4_preconditions(gate4_config)
    gate4_manifest = _gate4_manifest(gate4_config, gate4_run_id, gate4_mode, force)
    gate4_run_root = Path(gate4_manifest["run_root"])
    gate4_public_root = Path(gate4_manifest["public_root"])
    from bondalpha.cli import develop_alpha, evaluate_blind

    alpha_run = develop_alpha(alpha_config, gate3_public_root)
    alpha_spec = _freeze_or_reuse(alpha_run, alpha_config.paths.frozen_root, force=force)
    alpha_spec_id = alpha_spec.name
    release_gate4_public(gate4_run_root, alpha_spec_id)
    blind_output = Path("runs/alpha_gate4") / f"workflow-{alpha_spec_id}-{gate4_manifest['gate4_run_id']}"
    if (blind_output / "BLIND_LOCKED").exists() and not force:
        raise FileExistsError(f"blind evaluation already locked: {blind_output}. Use --force for a research rerun.")
    evaluate_blind(alpha_spec, gate4_public_root, blind_output)
    workflow_manifest = {
        "workflow": "gate4_alpha_factory_blinded_v1",
        "workflow_run_id": _workflow_id(preflight, gate4_manifest, alpha_spec_id),
        "gate3_public_root": str(gate3_public_root),
        "gate3_decision": preflight["gate3_decision"],
        "frozen_calibration_id": preflight["calibration_id"],
        "gate4_run_id": gate4_manifest["gate4_run_id"],
        "gate4_public_root": str(gate4_public_root),
        "gate4_quarantined_before_release": True,
        "alpha_run": str(alpha_run),
        "alpha_spec": str(alpha_spec),
        "alpha_spec_checksum_failures": verify_checksums(alpha_spec),
        "blind_output": str(blind_output),
        "blind_evaluation_sha256": file_sha256(blind_output / "BLIND_EVALUATION.json"),
        "truth_unblinded": False,
        "stage_order": [
            "verify_gate3_and_frozen_calibration",
            "generate_or_attach_quarantined_gate4",
            "develop_alpha_on_gate3_public",
            "freeze_alpha_spec",
            "release_gate4_public_to_frozen_alpha_spec",
            "evaluate_blind_once",
        ],
    }
    workflow_root = Path("runs/workflows") / workflow_manifest["workflow_run_id"]
    workflow_root.mkdir(parents=True, exist_ok=True)
    manifest_path = write_json(workflow_manifest, workflow_root / "workflow_manifest.json")
    _write_workflow_report(workflow_root, workflow_manifest)
    return BlindedWorkflowResult(
        workflow_run_id=workflow_manifest["workflow_run_id"],
        workflow_root=workflow_root,
        gate4_run_id=gate4_manifest["gate4_run_id"],
        alpha_run=alpha_run,
        alpha_spec=alpha_spec,
        blind_output=blind_output,
        manifest_path=manifest_path,
    )


def _gate4_manifest(config: BondSimConfig, gate4_run_id: str | None, mode: str, force: bool) -> dict[str, Any]:
    if gate4_run_id:
        return finalize_gate4_run(Path("runs/gate4") / gate4_run_id)
    return run_gate4(config, mode=mode, force=force)


def _freeze_or_reuse(alpha_run: Path, frozen_root: Path, *, force: bool) -> Path:
    manifest = json.loads((alpha_run / "alpha_manifest.json").read_text())
    alpha_spec_id = "alpha-spec-" + stable_json_hash(manifest)[:12]
    alpha_spec = frozen_root / alpha_spec_id
    if alpha_spec.exists() and not force:
        if (alpha_spec / "FROZEN").exists() and not verify_checksums(alpha_spec):
            return alpha_spec
        raise FileExistsError(f"alpha spec exists but is not valid: {alpha_spec}")
    return freeze_alpha_spec(alpha_run, frozen_root, force=force)


def _workflow_id(preflight: dict[str, Any], gate4_manifest: dict[str, Any], alpha_spec_id: str) -> str:
    payload = {
        "preflight": {
            "calibration_id": preflight["calibration_id"],
            "source_fingerprint": preflight["frozen_source_fingerprint"],
            "resolved_config_hash": preflight["frozen_resolved_config_hash"],
        },
        "gate4_run_id": gate4_manifest["gate4_run_id"],
        "alpha_spec_id": alpha_spec_id,
    }
    return "workflow-" + stable_json_hash(payload)[:16]


def _write_workflow_report(workflow_root: Path, manifest: dict[str, Any]) -> None:
    rows = "\n".join(f"- {stage}" for stage in manifest["stage_order"])
    (workflow_root / "workflow_report.md").write_text(
        "# Blinded Workflow Run\n\n"
        f"- workflow_run_id: `{manifest['workflow_run_id']}`\n"
        f"- frozen_calibration_id: `{manifest['frozen_calibration_id']}`\n"
        f"- gate4_run_id: `{manifest['gate4_run_id']}`\n"
        f"- alpha_spec: `{manifest['alpha_spec']}`\n"
        f"- blind_output: `{manifest['blind_output']}`\n"
        f"- truth_unblinded: `{manifest['truth_unblinded']}`\n\n"
        "## Stage Order\n\n"
        f"{rows}\n"
    )
