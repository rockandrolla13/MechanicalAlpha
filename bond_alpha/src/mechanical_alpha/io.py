"""Deterministic public artifact I/O helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from mechanical_alpha.hashing import file_sha256, stable_json_hash


def write_parquet(frame: pd.DataFrame, path: Path, compression: str = "zstd") -> Path:
    """Write a DataFrame to parquet through an atomic same-directory replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False, compression=compression)
    tmp.replace(path)
    return path


def write_json(value: dict[str, Any], path: Path) -> Path:
    """Write a deterministic JSON artifact through an atomic same-directory replace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, default=str))
    tmp.replace(path)
    return path


def manifest_for_files(files: list[Path], extra: dict[str, Any]) -> dict[str, Any]:
    """Build a manifest with file hashes for paths that exist."""

    return {
        **extra,
        "config_hash": stable_json_hash(extra.get("config", {})),
        "files": [
            {"path": str(path), "sha256": file_sha256(path), "bytes": path.stat().st_size}
            for path in files
            if path.exists()
        ],
    }
