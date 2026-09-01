"""Public synthetic-data adapter.

This module names the simulator dependency explicitly: it may read public
synthetic partitions, but it must never read truth partitions.
"""

from __future__ import annotations

from pathlib import Path

from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.data.synthetic import load_synthetic_bundle


def load_public_synthetic_bundle(scenario_root: str | Path) -> AlphaInputBundle:
    """Load a public synthetic scenario into the canonical alpha bundle."""

    return load_synthetic_bundle(scenario_root)
