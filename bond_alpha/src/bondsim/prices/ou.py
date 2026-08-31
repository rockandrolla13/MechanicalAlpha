"""Exact irregular-time OU transition."""

from __future__ import annotations

import numpy as np


def ou_step(x: float, delta_days: float, half_life_days: float, sigma: float, rng: np.random.Generator) -> float:
    kappa = np.log(2.0) / max(half_life_days, 1e-8)
    decay = np.exp(-kappa * max(delta_days, 0.0))
    variance = sigma**2 * (1.0 - np.exp(-2.0 * kappa * max(delta_days, 0.0))) / (2.0 * kappa)
    return float(decay * x + np.sqrt(max(variance, 0.0)) * rng.normal())
