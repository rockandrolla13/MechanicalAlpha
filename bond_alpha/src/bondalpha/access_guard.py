"""Guards that prevent alpha development from reading truth data."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from mechanical_alpha.public_policy import (
    TRUTH_COLUMN_TOKENS,
    TRUTH_PATH_TOKENS,
    assert_no_truth_columns as _assert_no_truth_columns,
    assert_public_path as _assert_public_path,
)


def assert_public_path(path: str | Path) -> None:
    _assert_public_path(path)


def assert_no_truth_columns(columns: Iterable[str]) -> None:
    _assert_no_truth_columns(columns)
