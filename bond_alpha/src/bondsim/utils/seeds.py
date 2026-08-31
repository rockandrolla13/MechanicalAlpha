"""Deterministic random stream allocation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


STREAM_NAMES = (
    "universe",
    "activity",
    "hawkes_immigrants",
    "hawkes_offspring",
    "marks",
    "curves",
    "ou",
    "impact",
    "output",
)


@dataclass(frozen=True)
class SeedBank:
    """Named random streams derived from one master seed."""

    master_seed: int
    streams: dict[str, int]

    @classmethod
    def create(cls, master_seed: int) -> "SeedBank":
        children = np.random.SeedSequence(master_seed).spawn(len(STREAM_NAMES))
        streams = {
            name: int(child.generate_state(1, dtype=np.uint32)[0])
            for name, child in zip(STREAM_NAMES, children, strict=True)
        }
        return cls(master_seed=master_seed, streams=streams)

    def rng(self, name: str) -> np.random.Generator:
        if name not in self.streams:
            raise KeyError(f"Unknown seed stream: {name}")
        return np.random.default_rng(self.streams[name])
