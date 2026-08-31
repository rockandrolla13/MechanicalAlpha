"""Guards that prevent alpha development from reading truth data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


TRUTH_PATH_TOKENS = ("synthetic_truth", "truth", "event_truth", "parameter_truth")
TRUTH_COLUMN_TOKENS = ("truth", "latent_", "planted_", "hawkes_parent", "hawkes_cluster")


def assert_public_path(path: str | Path) -> None:
    text = str(path).lower()
    for token in TRUTH_PATH_TOKENS:
        if token in text:
            raise PermissionError(f"alpha code may not read truth path: {path}")


def assert_no_truth_columns(columns: Iterable[str]) -> None:
    bad = []
    for column in columns:
        lower = str(column).lower()
        if any(token in lower for token in TRUTH_COLUMN_TOKENS):
            bad.append(str(column))
    if bad:
        raise PermissionError(f"alpha code received forbidden truth columns: {bad}")
