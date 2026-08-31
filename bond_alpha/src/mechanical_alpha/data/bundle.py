"""Helpers for building canonical alpha input bundles."""

from __future__ import annotations

import pandas as pd

from mechanical_alpha.contracts import AlphaInputBundle, FieldStatus, SourceMetadata


def bundle_from_frames(
    *,
    bonds: pd.DataFrame,
    events: pd.DataFrame,
    metadata: SourceMetadata,
    availability: dict[str, FieldStatus] | None = None,
    quotes: pd.DataFrame | None = None,
    fair_values: pd.DataFrame | None = None,
    rfqs: pd.DataFrame | None = None,
    external_factors: pd.DataFrame | None = None,
) -> AlphaInputBundle:
    """Create and validate an alpha input bundle from canonical frames."""

    bundle = AlphaInputBundle(
        bonds=bonds.copy(),
        events=events.copy(),
        metadata=metadata,
        availability=availability or {},
        quotes=None if quotes is None else quotes.copy(),
        fair_values=None if fair_values is None else fair_values.copy(),
        rfqs=None if rfqs is None else rfqs.copy(),
        external_factors=None if external_factors is None else external_factors.copy(),
    )
    bundle.validate()
    return bundle

