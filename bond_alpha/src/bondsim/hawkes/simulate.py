"""Sparse Poisson-cluster Hawkes simulation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bondsim.activity import intraday_bucket_probabilities
from bondsim.hawkes.graph import HawkesGraph


@dataclass(frozen=True)
class ClockEvent:
    clock_event_id: str
    session_idx: int
    seconds: float
    synthetic_bond_id: str
    synthetic_issuer_id: str
    side: int
    cluster_id: str
    parent_event_id: str | None
    generation: int
    edge_class: str
    is_immigrant: bool


def simulate_session_clock(
    universe: pd.DataFrame,
    graph: HawkesGraph,
    session_idx: int,
    daily_multiplier: float,
    rng_immigrants: np.random.Generator,
    rng_offspring: np.random.Generator,
    safety_cap: int,
) -> list[ClockEvent]:
    events: list[ClockEvent] = []
    queue: list[ClockEvent] = []
    bucket_probs = intraday_bucket_probabilities(13)
    bucket_edges = np.linspace(0, 6.5 * 3600, 14)
    issuer_by_bond = dict(zip(universe["synthetic_bond_id"].astype(str), universe["synthetic_issuer_id"].astype(str), strict=False))
    followers_by_issuer: dict[str, list[str]] = {}
    if graph.leader_follower_mass:
        followers = universe.loc[universe["is_leadlag_follower"].astype(bool), ["synthetic_issuer_id", "synthetic_bond_id"]]
        for issuer, group in followers.groupby("synthetic_issuer_id", sort=False):
            followers_by_issuer[str(issuer)] = group["synthetic_bond_id"].astype(str).tolist()
    for _, bond in universe.iterrows():
        expected = float(bond["target_events_per_day"]) * daily_multiplier
        count = rng_immigrants.poisson(max(expected, 0.0))
        buckets = rng_immigrants.choice(len(bucket_probs), size=count, p=bucket_probs)
        for local_idx, bucket in enumerate(buckets):
            seconds = rng_immigrants.uniform(bucket_edges[bucket], bucket_edges[bucket + 1])
            side = 1 if rng_immigrants.random() < 0.5 else -1
            clock_id = f"K{session_idx:04d}_{bond.name}_{local_idx}_0"
            event = ClockEvent(
                clock_event_id=clock_id,
                session_idx=session_idx,
                seconds=float(seconds),
                synthetic_bond_id=str(bond["synthetic_bond_id"]),
                synthetic_issuer_id=str(bond["synthetic_issuer_id"]),
                side=side,
                cluster_id=f"C{session_idx:04d}_{bond.name}_{local_idx}",
                parent_event_id=None,
                generation=0,
                edge_class="immigrant",
                is_immigrant=True,
            )
            events.append(event)
            queue.append(event)
    cursor = 0
    while cursor < len(queue):
        parent = queue[cursor]
        cursor += 1
        if len(events) > safety_cap:
            raise RuntimeError(f"Hawkes safety cap hit in session {session_idx}: {len(events)} events")
        child_specs = [(parent.synthetic_bond_id, parent.side, graph.same_side_mass, "same_bond_same_side")]
        child_specs.append((parent.synthetic_bond_id, -parent.side, graph.opposite_side_mass, "same_bond_opposite_side"))
        if graph.leader_follower_mass:
            siblings = [
                bond_id for bond_id in followers_by_issuer.get(parent.synthetic_issuer_id, [])
                if bond_id != parent.synthetic_bond_id
            ]
            for sibling in siblings[:3]:
                child_specs.append((sibling, parent.side, graph.leader_follower_mass, "issuer_leader_to_follower_same_side"))
        for bond_id, side, mass, edge_class in child_specs:
            for half_life in graph.half_lives_minutes:
                alpha = mass / len(graph.half_lives_minutes)
                for _ in range(rng_offspring.poisson(alpha)):
                    delay = rng_offspring.exponential(half_life * 60 / np.log(2.0))
                    seconds = parent.seconds + delay
                    if seconds >= 6.5 * 3600:
                        continue
                    issuer_id = issuer_by_bond[str(bond_id)]
                    child = ClockEvent(
                        clock_event_id=f"{parent.clock_event_id}_{len(events)}",
                        session_idx=session_idx,
                        seconds=float(seconds),
                        synthetic_bond_id=str(bond_id),
                        synthetic_issuer_id=issuer_id,
                        side=int(side),
                        cluster_id=parent.cluster_id,
                        parent_event_id=parent.clock_event_id,
                        generation=parent.generation + 1,
                        edge_class=edge_class,
                        is_immigrant=False,
                    )
                    events.append(child)
                    queue.append(child)
    return sorted(events, key=lambda event: (event.seconds, event.synthetic_bond_id, event.side, event.clock_event_id))
