"""Availability registry for alpha inputs and factors."""

from __future__ import annotations

from dataclasses import dataclass

from mechanical_alpha.contracts import AlphaInputBundle, FieldStatus
from mechanical_alpha.schema import Availability


@dataclass(frozen=True)
class FactorSpec:
    """Static declaration for one alpha factor."""

    factor_id: str
    name: str
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class FactorCapability:
    """Resolved capability for one factor against one bundle."""

    factor_id: str
    name: str
    availability: Availability
    missing_fields: tuple[str, ...]
    ambiguous_fields: tuple[str, ...]
    notes: str


def classify_field(bundle: AlphaInputBundle, field: str) -> FieldStatus:
    if field in bundle.availability:
        return bundle.availability[field]
    for table in bundle.public_tables().values():
        if field in table.columns:
            return FieldStatus(field=field, availability=Availability.DIRECT, source="canonical")
    return FieldStatus(field=field, availability=Availability.UNAVAILABLE, source=None)


def evaluate_factor(bundle: AlphaInputBundle, spec: FactorSpec) -> FactorCapability:
    statuses = [classify_field(bundle, field) for field in spec.required_fields]
    missing = tuple(status.field for status in statuses if status.availability == Availability.UNAVAILABLE)
    ambiguous = tuple(status.field for status in statuses if status.availability == Availability.AMBIGUOUS)
    partial = tuple(status.field for status in statuses if status.availability == Availability.PARTIAL)

    if missing:
        availability = Availability.UNAVAILABLE
    elif ambiguous:
        availability = Availability.AMBIGUOUS
    elif partial:
        availability = Availability.PARTIAL
    elif any(status.availability == Availability.DERIVABLE for status in statuses):
        availability = Availability.DERIVABLE
    else:
        availability = Availability.DIRECT

    return FactorCapability(
        factor_id=spec.factor_id,
        name=spec.name,
        availability=availability,
        missing_fields=missing,
        ambiguous_fields=ambiguous,
        notes=spec.notes,
    )


def evaluate_registry(bundle: AlphaInputBundle, specs: list[FactorSpec]) -> list[FactorCapability]:
    return [evaluate_factor(bundle, spec) for spec in specs]

