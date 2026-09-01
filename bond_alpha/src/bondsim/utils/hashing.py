"""Stable hashes for manifests.

Compatibility wrapper around the neutral MechanicalAlpha hash helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mechanical_alpha.hashing import file_sha256 as _file_sha256
from mechanical_alpha.hashing import stable_json_hash as _stable_json_hash


def stable_json_hash(value: Any) -> str:
    return _stable_json_hash(value)


def file_sha256(path: Path) -> str:
    return _file_sha256(path)
