"""Stable hashing helpers for public MechanicalAlpha artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_json_hash(value: Any) -> str:
    """Return a deterministic SHA-256 hash for a JSON-serializable value."""

    payload = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: Path) -> str:
    """Return a SHA-256 hash of a file's byte content."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
