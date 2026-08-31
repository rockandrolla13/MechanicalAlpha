"""Small CLI for checking alpha data availability."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from mechanical_alpha.availability import evaluate_registry
from mechanical_alpha.data.synthetic import load_synthetic_bundle
from mechanical_alpha.registry import default_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mechanical-alpha")
    subparsers = parser.add_subparsers(dest="command", required=True)
    availability = subparsers.add_parser("availability")
    availability.add_argument("--synthetic-root", type=Path, required=True)
    availability.add_argument("--output", type=Path)
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
    raise ValueError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

