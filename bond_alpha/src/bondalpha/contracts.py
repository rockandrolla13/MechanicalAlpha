"""Public Alpha Factory contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AlphaSpecReference:
    """Reference to an immutable frozen alpha specification."""

    alpha_spec_id: str
    path: Path


@dataclass(frozen=True)
class BlindEvaluationReference:
    """Reference to a locked blind Gate 4 alpha evaluation."""

    run_id: str
    path: Path
    locked: bool
