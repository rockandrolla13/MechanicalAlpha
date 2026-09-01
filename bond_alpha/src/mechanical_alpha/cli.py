"""Small CLI for checking alpha data availability."""

from __future__ import annotations

import argparse
import importlib
from pathlib import Path

import pandas as pd
import yaml

from mechanical_alpha.availability import evaluate_registry
from mechanical_alpha.data.synthetic import load_synthetic_bundle
from mechanical_alpha.registry import default_registry, standalone_alpha_index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mechanical-alpha")
    subparsers = parser.add_subparsers(dest="command", required=True)
    availability = subparsers.add_parser("availability")
    availability.add_argument("--synthetic-root", type=Path, required=True)
    availability.add_argument("--output", type=Path)
    compute = subparsers.add_parser("compute")
    compute.add_argument("--synthetic-root", type=Path, required=True)
    compute.add_argument("--alphas", default="all", help="Comma-separated alpha ids, or all implemented standalone alphas.")
    compute.add_argument("--alpha-config", type=Path, help="Optional YAML config for a selected standalone alpha.")
    compute.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "availability":
        bundle = load_synthetic_bundle(args.synthetic_root)
        rows = [capability.__dict__ for capability in evaluate_registry(bundle, default_registry())]
        frame = pd.DataFrame(rows)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(args.output, index=False)
        else:
            print(frame.to_string(index=False))
        return 0
    if args.command == "compute":
        bundle = load_synthetic_bundle(args.synthetic_root)
        requested = _selected_alpha_entries(args.alphas)
        frames: list[pd.DataFrame] = []
        for entry in requested:
            module = importlib.import_module(entry.module)
            if not hasattr(module, "compute"):
                raise ValueError(f"alpha {entry.alpha_id} has no compute() function")
            alpha_config = _load_alpha_config(module, args.alpha_config)
            values = module.compute(bundle, config=alpha_config) if alpha_config is not None else module.compute(bundle)
            if values.empty:
                continue
            values = values.copy()
            values.insert(0, "alpha_id", entry.alpha_id)
            frames.append(values)
        output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["alpha_id"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output.to_parquet(args.output, index=False)
        return 0
    raise ValueError(f"unknown command: {args.command}")


def _selected_alpha_entries(selection: str) -> list[object]:
    index = {entry.alpha_id: entry for entry in standalone_alpha_index()}
    if selection == "all":
        return [entry for entry in index.values() if entry.status == "implemented"]
    ids = [item.strip() for item in selection.split(",") if item.strip()]
    missing = [alpha_id for alpha_id in ids if alpha_id not in index]
    if missing:
        raise ValueError(f"unknown alpha ids: {missing}")
    entries = [index[alpha_id] for alpha_id in ids]
    blocked = [entry.alpha_id for entry in entries if entry.status != "implemented"]
    if blocked:
        raise ValueError(f"requested alphas are not implemented: {blocked}")
    return entries


def _load_alpha_config(module: object, path: Path | None) -> object | None:
    if path is None:
        return None
    if not hasattr(module, "config_from_mapping"):
        raise ValueError(f"module {module.__name__} does not support --alpha-config")
    payload = yaml.safe_load(path.read_text()) or {}
    return module.config_from_mapping(payload)


if __name__ == "__main__":
    raise SystemExit(main())
