"""Canonical public-data safety policy shared by simulator and alpha code."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


TRUTH_PATH_TOKENS = (
    "synthetic_truth",
    "truth",
    "event_truth",
    "parameter_truth",
)

TRUTH_COLUMN_TOKENS = (
    "truth",
    "latent_",
    "planted_",
    "hawkes_parent",
    "hawkes_cluster",
)

TRUTH_FORBIDDEN_COLUMNS = frozenset(
    {
        "truth",
        "truth_label",
        "latent_fair_value",
        "latent_mid",
        "latent_mid_with_planted_effects",
        "latent_mid_without_planted_effects",
        "ou_pressure",
        "permanent_impact_state",
        "ordinary_temporary_impact_state",
        "planted_effect_ids",
        "planted_large_print_state",
        "planted_leadlag_state",
        "transaction_concession",
        "observation_noise",
        "hawkes_parent_event_id",
        "hawkes_cluster_id",
        "hawkes_generation",
        "hawkes_edge_class",
        "is_immigrant",
        "large_print_threshold",
        "is_large_print",
        "source_leader_event_id",
    }
)

SOURCE_IDENTIFIER_COLUMNS = frozenset(
    {
        "source_bond_id",
        "source_issuer_id",
        "cusip",
        "isin",
        "client_id",
        "dealer_id",
        "account_id",
    }
)

FORBIDDEN_PUBLIC_COLUMNS = TRUTH_FORBIDDEN_COLUMNS.union(SOURCE_IDENTIFIER_COLUMNS)


def assert_public_path(path: str | Path) -> None:
    """Raise PermissionError when a path points at truth or latent-state data."""

    text = str(path).lower()
    for token in TRUTH_PATH_TOKENS:
        if token in text:
            raise PermissionError(f"alpha code may not read truth path: {path}")


def assert_no_truth_columns(columns: Iterable[str]) -> None:
    """Raise PermissionError when columns contain truth-like fields."""

    bad = truth_like_columns(columns)
    if bad:
        raise PermissionError(f"alpha code received forbidden truth columns: {bad}")


def assert_public_columns(columns: Iterable[str]) -> None:
    """Raise ValueError when a public output schema exposes forbidden fields."""

    leaked = sorted(FORBIDDEN_PUBLIC_COLUMNS.intersection(set(map(str, columns))))
    if leaked:
        raise ValueError(f"public output contains forbidden columns: {leaked}")
    token_leaks = truth_like_columns(columns)
    if token_leaks:
        raise ValueError(f"public output contains truth-like columns: {token_leaks}")


def truth_like_columns(columns: Iterable[str]) -> list[str]:
    """Return columns whose names match forbidden truth-token patterns."""

    bad = []
    for column in columns:
        lower = str(column).lower()
        if any(token in lower for token in TRUTH_COLUMN_TOKENS):
            bad.append(str(column))
    return sorted(set(bad))
