"""Deterministic feature library for corporate-bond alpha research."""

from mechanical_alpha.features.diagnostics import FeatureDiagnostic, diagnose_feature_frame
from mechanical_alpha.features.microstructure import (
    DEFAULT_CALENDAR_WINDOWS,
    DEFAULT_EVENT_WINDOWS,
    FeatureDefinition,
    compute_microstructure_features,
    microstructure_feature_registry,
)

__all__ = [
    "DEFAULT_CALENDAR_WINDOWS",
    "DEFAULT_EVENT_WINDOWS",
    "FeatureDefinition",
    "FeatureDiagnostic",
    "compute_microstructure_features",
    "diagnose_feature_frame",
    "microstructure_feature_registry",
]
