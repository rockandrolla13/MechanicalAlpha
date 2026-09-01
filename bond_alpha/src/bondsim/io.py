"""Parquet and manifest IO.

Compatibility wrapper around neutral MechanicalAlpha artifact helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from mechanical_alpha.io import manifest_for_files as _manifest_for_files
from mechanical_alpha.io import write_json as _write_json
from mechanical_alpha.io import write_parquet as _write_parquet


def write_parquet(frame: pd.DataFrame, path: Path, compression: str = "zstd") -> Path:
    return _write_parquet(frame, path, compression)


def write_json(value: dict[str, Any], path: Path) -> Path:
    return _write_json(value, path)


def manifest_for_files(files: list[Path], extra: dict[str, Any]) -> dict[str, Any]:
    return _manifest_for_files(files, extra)
