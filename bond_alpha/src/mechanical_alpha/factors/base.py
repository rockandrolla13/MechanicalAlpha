"""Base interface for alpha factor implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from mechanical_alpha.availability import FactorCapability, FactorSpec, evaluate_factor
from mechanical_alpha.contracts import AlphaInputBundle


@dataclass(frozen=True)
class FactorResult:
    """Observable factor output."""

    spec: FactorSpec
    capability: FactorCapability
    values: pd.DataFrame


class Factor(Protocol):
    """A factor computes observable values from an alpha input bundle."""

    spec: FactorSpec

    def compute(self, bundle: AlphaInputBundle) -> FactorResult:
        """Compute factor values using only canonical public tables."""


def blocked_result(bundle: AlphaInputBundle, spec: FactorSpec) -> FactorResult:
    """Return an empty result for factors that cannot run on this bundle."""

    capability = evaluate_factor(bundle, spec)
    return FactorResult(spec=spec, capability=capability, values=pd.DataFrame())

