"""Command line interface for bondsim."""

from __future__ import annotations

import argparse
from pathlib import Path

from bondsim.config import load_config
from bondsim.calibration.compare import compare_runs
from bondsim.calibration.ensemble import reproduce_calibration, report_calibration, run_calibration
from bondsim.calibration.freeze import freeze_calibration
from bondsim.pipeline import (
    DiscoveryPipeline,
    FitPipeline,
    PreparationPipeline,
    SimulationPipeline,
    ValidationPipeline,
    run_full_pipeline,
)
from bondsim.gate4 import finalize_gate4_run, release_gate4_public, run_gate4
from bondsim.gate4_generation import run_gate4_production_generation
from bondsim.gate4_readiness import run_gate4_readiness_audit
from bondsim.validation.medium import run_medium_gate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bondsim")
    sub = parser.add_subparsers(dest="command", required=True)
    calibration = sub.add_parser("calibration")
    calibration_sub = calibration.add_subparsers(dest="calibration_command", required=True)
    calibration_run = calibration_sub.add_parser("run")
    calibration_run.add_argument("--config", default="configs/base.yaml")
    calibration_run.add_argument("--bonds", type=int, default=50)
    calibration_run.add_argument("--sessions", type=int, default=60)
    calibration_run.add_argument("--seeds", type=int, default=5)
    calibration_report = calibration_sub.add_parser("report")
    calibration_report.add_argument("--run", required=True)
    calibration_reproduce = calibration_sub.add_parser("reproduce")
    calibration_reproduce.add_argument("--run", required=True)
    calibration_reproduce.add_argument("--output", required=True)
    calibration_compare = calibration_sub.add_parser("compare")
    calibration_compare.add_argument("--left", required=True)
    calibration_compare.add_argument("--right", required=True)
    calibration_freeze = calibration_sub.add_parser("freeze")
    calibration_freeze.add_argument("--run", required=True)
    calibration_freeze.add_argument("--allow-dirty", action="store_true")
    calibration_freeze.add_argument("--force", action="store_true")
    gate4_release = sub.add_parser("gate4-release")
    gate4_release.add_argument("--run", required=True)
    gate4_release.add_argument("--alpha-spec-id", required=True)
    gate4_finalize = sub.add_parser("gate4-finalize")
    gate4_finalize.add_argument("--run", required=True)
    gate4_readiness = sub.add_parser("gate4-readiness")
    gate4_readiness.add_argument("--config", default="configs/gate4.yaml")
    gate4_production = sub.add_parser("gate4-production")
    gate4_production.add_argument("--config", default="configs/gate4_production.yaml")
    gate4_production.add_argument("--mode", default="full", choices=["smoke", "medium", "full"])
    gate4_production.add_argument("--force", action="store_true")
    for name in ["inspect", "prepare", "fit", "simulate", "validate", "pipeline", "gate3", "gate4"]:
        p = sub.add_parser(name)
        p.add_argument("--config", default="configs/base.yaml")
        p.add_argument("--mode", default="smoke", choices=["smoke", "quick", "medium", "full"])
        p.add_argument("--seed", type=int)
        p.add_argument("--data-root")
        p.add_argument("--output-root")
        p.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "calibration":
        if args.calibration_command == "run":
            config = load_config(args.config)
            result = run_calibration(config, bonds=args.bonds, sessions=args.sessions, seeds=args.seeds)
            print(f"calibration run_id={result.run_id} passed={result.passed} run_dir={result.run_dir}")
        elif args.calibration_command == "report":
            path = report_calibration(Path(args.run))
            print(f"calibration report={path}")
        elif args.calibration_command == "reproduce":
            result = reproduce_calibration(Path(args.run), Path(args.output))
            print(f"calibration reproduce output={args.output} matches={result['matches_source']}")
        elif args.calibration_command == "compare":
            result = compare_runs(Path(args.left), Path(args.right))
            print(f"calibration compare passed={result['passed']} report={result.get('report_markdown')}")
        elif args.calibration_command == "freeze":
            path = freeze_calibration(Path(args.run), allow_dirty=args.allow_dirty, force=args.force)
            print(f"calibration frozen={path}")
        return 0
    if args.command == "gate4-release":
        result = release_gate4_public(Path(args.run), args.alpha_spec_id)
        print(f"gate4 released run_id={result['gate4_run_id']} alpha_spec={args.alpha_spec_id}")
        return 0
    if args.command == "gate4-finalize":
        result = finalize_gate4_run(Path(args.run))
        print(f"gate4 finalized run_id={result['gate4_run_id']}")
        return 0
    if args.command == "gate4-readiness":
        config = load_config(args.config)
        result = run_gate4_readiness_audit(config)
        print(f"gate4_ready={result['gate4_ready']} report={config.paths.report_root / 'gate4' / 'readiness_audit.json'}")
        return 0
    if args.command == "gate4-production":
        config = load_config(args.config)
        result = run_gate4_production_generation(config, mode=args.mode, force=args.force)
        print(f"gate4 production run_id={result['gate4_run_id']} quarantined={result['quarantined']}")
        return 0
    config = load_config(args.config)
    if args.seed is not None:
        config.project.master_seed = args.seed
    if args.data_root:
        config.paths.data_root = args.data_root
    if args.output_root:
        root = Path(args.output_root)
        config.paths.synthetic_root = root / "synthetic"
        config.paths.truth_root = root / "synthetic_truth"
        config.paths.report_root = root / "reports"

    if args.command == "inspect":
        result = DiscoveryPipeline(config).run()
        print(f"discovery source={result.source_name} rows={result.profile.get('rows')}")
    elif args.command == "prepare":
        result = PreparationPipeline(config).run(mode=args.mode)
        print(f"prepared bonds={result.rows['bonds']} events={result.rows['events']}")
    elif args.command == "fit":
        result = FitPipeline(config).run(mode=args.mode)
        print(f"selected mark model={result.selected}")
    elif args.command == "simulate":
        result = SimulationPipeline(config).run(mode=args.mode, force=args.force)
        print(f"simulated {result.scenario} public={result.public_path}")
    elif args.command == "validate":
        result = ValidationPipeline(config).run(mode=args.mode)
        print(f"validation passed={result['passed']}")
    elif args.command == "pipeline":
        result = run_full_pipeline(config, mode=args.mode, force=args.force)
        if isinstance(result, list):
            scenarios = ", ".join(item.scenario for item in result)
            print(f"pipeline complete scenarios={scenarios}")
        else:
            print(f"pipeline complete scenario={result.scenario} public={result.public_path}")
    elif args.command == "gate3":
        if not config.frozen_calibration_id:
            raise SystemExit("Gate 3 requires frozen_calibration_id in the config. Use configs/gate3.yaml after Gate 2.5 freeze.")
        result = run_medium_gate(config, force=args.force)
        print(f"gate3 passed={result['passed']}")
    elif args.command == "gate4":
        if not config.frozen_calibration_id:
            raise SystemExit("Gate 4 requires frozen_calibration_id in the config.")
        result = run_gate4(config, mode=args.mode, force=args.force)
        print(f"gate4 run_id={result['gate4_run_id']} quarantined={result['quarantined']} public={result['public_root']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
