"""Public Alpha Factory access controls.

This module is the public name for the guard functions.  The older
``access_guard`` module remains as a compatibility shim for existing code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bondalpha.access_guard import assert_no_truth_columns, assert_public_path


def require_public_dataset_path(path: str | Path) -> None:
    """Raise if an alpha workflow tries to read a truth path."""

    assert_public_path(path)


def require_public_columns(columns: Iterable[str]) -> None:
    """Raise if a public alpha frame contains truth or latent-state columns."""

    assert_no_truth_columns(columns)


__all__ = [
    "assert_no_truth_columns",
    "assert_public_path",
    "require_public_columns",
    "require_public_dataset_path",
]
