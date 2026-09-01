"""Fit-and-score wrapper for the triplet research operator."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from mechanical_alpha.triplets.clocks import ClockIndex
from mechanical_alpha.triplets.inference import adjust_triplet_multiplicity, estimate_triplet_family, select_triplets
from mechanical_alpha.triplets.panel import build_triplet_panel, sample_state_on_clock
from mechanical_alpha.triplets.signal import aggregate_triplet_signals, score_triplet


@dataclass(frozen=True)
class TripletMethodSpec:
    """Frozen triplet search space."""

    lags: tuple[int, ...] = (1, 2)
    horizons: tuple[int, ...] = (1, 2)
    anchors: tuple[int, ...] = (0,)
    target_type: str = "clean_price"
    alpha: float = 0.05
    min_obs: int = 20
    multiplicity_method: str = "holm"
    value_col: str = "price"


@dataclass(frozen=True)
class FittedTripletMethod:
    """Train-fitted triplet selection artifact."""

    spec: TripletMethodSpec
    estimates: pd.DataFrame
    selected: pd.DataFrame
    train_panel: pd.DataFrame


def fit_triplet_method(state: pd.DataFrame, clock: ClockIndex, spec: TripletMethodSpec) -> FittedTripletMethod:
    """Fit the triplet method on one training state panel."""

    sampled = sample_state_on_clock(state, clock, value_col=spec.value_col)
    panel = build_triplet_panel(
        sampled,
        lags=spec.lags,
        horizons=spec.horizons,
        anchors=spec.anchors,
        value_col=spec.value_col,
        target_type=spec.target_type,
    )
    estimates = estimate_triplet_family(panel)
    estimates = adjust_triplet_multiplicity(estimates, method=spec.multiplicity_method)
    selected = select_triplets(estimates, alpha=spec.alpha, min_obs=spec.min_obs)
    return FittedTripletMethod(spec=spec, estimates=estimates, selected=selected, train_panel=panel)


def score_triplet_method(state: pd.DataFrame, clock: ClockIndex, fitted: FittedTripletMethod) -> pd.DataFrame:
    """Score a fitted triplet method on a later state panel."""

    sampled = sample_state_on_clock(state, clock, value_col=fitted.spec.value_col)
    panel = build_triplet_panel(
        sampled,
        lags=fitted.spec.lags,
        horizons=fitted.spec.horizons,
        anchors=fitted.spec.anchors,
        value_col=fitted.spec.value_col,
        target_type=fitted.spec.target_type,
    )
    scores = score_triplet(panel, fitted.selected, train_panel=fitted.train_panel)
    return aggregate_triplet_signals(scores)

