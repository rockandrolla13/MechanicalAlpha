"""Mark-model visualization data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def notional_tail_table(events: pd.DataFrame, quantiles: np.ndarray | None = None) -> pd.DataFrame:
    """Return deterministic notional tail quantiles."""

    qs = quantiles if quantiles is not None else np.linspace(0.80, 0.995, 30)
    return pd.DataFrame({"quantile": qs, "notional": [float(events["notional"].quantile(q)) for q in qs]})
