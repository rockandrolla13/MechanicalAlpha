"""Typed contracts at the portable alpha seam."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from mechanical_alpha.schema import (
    BONDS_SCHEMA,
    EVENTS_SCHEMA,
    EXTERNAL_FACTORS_SCHEMA,
    FAIR_VALUES_SCHEMA,
    QUOTES_SCHEMA,
    RFQS_SCHEMA,
    SOURCE_IDENTIFIER_COLUMNS,
    TRUTH_FORBIDDEN_COLUMNS,
    Availability,
    SideConvention,
    TableSchema,
)


@dataclass(frozen=True)
class FieldStatus:
    """Availability and provenance for one canonical field."""

    field: str
    availability: Availability
    source: str | None = None
    note: str = ""


@dataclass(frozen=True)
class SourceMetadata:
    """Source-level metadata that factors can inspect without source-specific code."""

    name: str
    side_convention: SideConvention
    side_semantics: str
    price_units: str
    size_units: str
    point_in_time_safety: str
    limitations: tuple[str, ...] = ()


@dataclass
class AlphaInputBundle:
    """Canonical input bundle consumed by alpha factors.

    Source adapters own raw field names and source-specific semantics.
    Factor code consumes only this bundle.
    """

    bonds: pd.DataFrame
    events: pd.DataFrame
    metadata: SourceMetadata
    availability: dict[str, FieldStatus] = field(default_factory=dict)
    quotes: pd.DataFrame | None = None
    fair_values: pd.DataFrame | None = None
    rfqs: pd.DataFrame | None = None
    external_factors: pd.DataFrame | None = None

    def validate(self) -> None:
        """Raise ValueError when the bundle violates the canonical contract."""

        _validate_table(self.bonds, BONDS_SCHEMA)
        _validate_table(self.events, EVENTS_SCHEMA)
        if self.quotes is not None:
            _validate_table(self.quotes, QUOTES_SCHEMA)
        if self.fair_values is not None:
            _validate_table(self.fair_values, FAIR_VALUES_SCHEMA)
        if self.rfqs is not None:
            _validate_table(self.rfqs, RFQS_SCHEMA)
        if self.external_factors is not None:
            _validate_table(self.external_factors, EXTERNAL_FACTORS_SCHEMA)
        _validate_side(self.events)
        _validate_no_forbidden_columns(self.public_tables())

    def public_tables(self) -> dict[str, pd.DataFrame]:
        """Return public observable tables only."""

        tables = {"bonds": self.bonds, "events": self.events}
        if self.quotes is not None:
            tables["quotes"] = self.quotes
        if self.fair_values is not None:
            tables["fair_values"] = self.fair_values
        if self.rfqs is not None:
            tables["rfqs"] = self.rfqs
        if self.external_factors is not None:
            tables["external_factors"] = self.external_factors
        return tables

    def to_parquet(self, root: str | Path) -> None:
        """Write canonical public tables to parquet files."""

        output_root = Path(root)
        output_root.mkdir(parents=True, exist_ok=True)
        for name, table in self.public_tables().items():
            table.to_parquet(output_root / f"{name}.parquet", index=False)

    @classmethod
    def from_parquet(cls, root: str | Path, metadata: SourceMetadata) -> "AlphaInputBundle":
        """Load a bundle previously written by `to_parquet`."""

        input_root = Path(root)
        kwargs: dict[str, Any] = {
            "bonds": pd.read_parquet(input_root / "bonds.parquet"),
            "events": pd.read_parquet(input_root / "events.parquet"),
            "metadata": metadata,
        }
        for name in ("quotes", "fair_values", "rfqs", "external_factors"):
            path = input_root / f"{name}.parquet"
            if path.exists():
                kwargs[name] = pd.read_parquet(path)
        bundle = cls(**kwargs)
        bundle.validate()
        return bundle


def _validate_table(frame: pd.DataFrame, schema: TableSchema) -> None:
    missing = [column for column in schema.required if column not in frame.columns]
    if missing:
        raise ValueError(f"{schema.name} missing required columns: {missing}")


def _validate_side(events: pd.DataFrame) -> None:
    valid_values = {-1, 0, 1}
    observed = set(events["side"].dropna().astype(int).unique().tolist())
    invalid = observed.difference(valid_values)
    if invalid:
        raise ValueError(f"events.side contains invalid values: {sorted(invalid)}")


def _validate_no_forbidden_columns(tables: dict[str, pd.DataFrame]) -> None:
    forbidden = TRUTH_FORBIDDEN_COLUMNS.union(SOURCE_IDENTIFIER_COLUMNS)
    for name, table in tables.items():
        leaked = sorted(forbidden.intersection(table.columns))
        if leaked:
            raise ValueError(f"{name} contains forbidden public columns: {leaked}")

