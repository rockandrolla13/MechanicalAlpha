"""Shared deterministic Matplotlib theme."""

from __future__ import annotations

import matplotlib.pyplot as plt


def apply_theme() -> None:
    """Apply one fixed plotting theme."""

    plt.rcParams.update(
        {
            "figure.figsize": (8, 4.8),
            "font.size": 10,
            "axes.grid": True,
            "axes.titlesize": 12,
            "axes.labelsize": 10,
            "savefig.dpi": 120,
            "savefig.bbox": "tight",
        }
    )
