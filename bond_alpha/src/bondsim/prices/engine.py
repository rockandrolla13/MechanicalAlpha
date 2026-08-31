"""Price construction with auditable planted effects."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from bondsim.config import BondSimConfig
from bondsim.hawkes.simulate import ClockEvent
from bondsim.prices.ou import ou_step
from bondsim.scenarios import ScenarioFlags


@dataclass
class BondPriceState:
    fair_value: float = 100.0
    ou_pressure: float = 0.0
    permanent_impact: float = 0.0
    ordinary_temp: float = 0.0
    large_temp: float = 0.0
    leadlag: float = 0.0
    last_seconds: float = 0.0
    last_session_idx: int = -1


class PriceEngine:
    """Maintains event-time price states and truth components."""

    def __init__(self, universe: pd.DataFrame, config: BondSimConfig, flags: ScenarioFlags, rng: np.random.Generator):
        self.universe = universe.set_index("synthetic_bond_id")
        self.config = config
        self.flags = flags
        self.rng = rng
        issuer_base = {
            issuer_id: float(100 + rng.normal(0, 1.25))
            for issuer_id in self.universe["synthetic_issuer_id"].unique()
        }
        self.states = {}
        for bond_id, row in self.universe.iterrows():
            base = issuer_base[str(row["synthetic_issuer_id"])] + float(rng.normal(0, 0.20))
            self.states[bond_id] = BondPriceState(fair_value=base)
        self.large_thresholds = self.universe["notional_p90"].fillna(self.universe["median_notional"].median()).to_dict()
        self.followers_by_issuer = {
            str(issuer): group.index.astype(str).tolist()
            for issuer, group in self.universe[self.universe["is_leadlag_follower"].astype(bool)].groupby("synthetic_issuer_id")
        }
        pc = config.positive_controls
        self.reversal_amp = float(pc["large_print_reversal"]["default_amplitude_price_points"])
        self.reversal_half_life = float(pc["large_print_reversal"]["half_life_days"])
        self.leadlag_amp = float(pc["leader_follower"]["default_peak_price_points"])

    def price_event(self, clock_event: ClockEvent, mark: dict[str, object], event_id: str) -> tuple[dict[str, object], dict[str, object]]:
        state = self.states[clock_event.synthetic_bond_id]
        if state.last_session_idx != clock_event.session_idx:
            session_gap = max(1, clock_event.session_idx - state.last_session_idx)
            state.fair_value += float(self.rng.normal(0.0, 0.025 * np.sqrt(session_gap)))
            state.last_seconds = 0.0
            state.last_session_idx = clock_event.session_idx
        delta_days = (clock_event.seconds - state.last_seconds) / (6.5 * 3600)
        state.ou_pressure = ou_step(state.ou_pressure, delta_days, 2.0, 0.03, self.rng)
        decay = 2 ** (-max(delta_days, 0.0) / self.reversal_half_life)
        state.ordinary_temp *= decay
        state.large_temp *= decay
        state.leadlag *= decay
        state.last_seconds = clock_event.seconds

        notional = float(mark["notional"])
        threshold = float(self.large_thresholds.get(clock_event.synthetic_bond_id, np.nan))
        if not np.isfinite(threshold) or threshold <= 0:
            threshold = max(notional, 1.0)
        normalized_size = min(4.0, np.sqrt(notional / max(threshold, 1.0)))
        is_large = notional >= threshold
        base_mid = state.fair_value + state.ou_pressure + state.permanent_impact + state.ordinary_temp
        pre_large_temp = state.large_temp
        pre_leadlag = state.leadlag
        latent_without_planted = base_mid
        latent_with_planted = base_mid + pre_large_temp + pre_leadlag
        concession = 0.015 * clock_event.side * normalized_size
        noise = float(self.rng.normal(0.0, 0.015))
        immediate_planted = clock_event.side * self.reversal_amp * normalized_size if self.flags.reversal and is_large else 0.0
        price = latent_with_planted + immediate_planted + concession + noise

        planted_ids: list[str] = []
        if self.flags.reversal and is_large:
            state.large_temp += clock_event.side * self.reversal_amp * normalized_size
            planted_ids.append("large_print_reversal")
        state.ordinary_temp += clock_event.side * 0.015 * normalized_size
        state.permanent_impact += clock_event.side * 0.001 * normalized_size

        if self.flags.leadlag and self.universe.loc[clock_event.synthetic_bond_id, "is_issuer_leader"]:
            followers = [
                follower for follower in self.followers_by_issuer.get(clock_event.synthetic_issuer_id, [])
                if follower != clock_event.synthetic_bond_id
            ]
            for follower in followers:
                self.states[follower].leadlag += clock_event.side * self.leadlag_amp * normalized_size
            planted_ids.append("leader_follower")

        public = {
            "event_id": event_id,
            "side": clock_event.side,
            "notional": notional,
            "price": float(price),
            "is_interdealer": bool(mark["is_interdealer"]),
            "trade_type": str(mark["trade_type"]),
            "venue_bucket": str(mark["venue_bucket"]),
            "reporting_delay_ms": float(mark["reporting_delay_ms"]),
            "currency": "USD",
        }
        truth = {
            "event_id": event_id,
            "latent_fair_value": state.fair_value,
            "ou_pressure": state.ou_pressure,
            "permanent_impact_state": state.permanent_impact,
            "ordinary_temporary_impact_state": state.ordinary_temp,
            "planted_large_print_state": pre_large_temp,
            "planted_leadlag_state": pre_leadlag,
            "latent_mid_without_planted_effects": latent_without_planted,
            "latent_mid_with_planted_effects": latent_with_planted,
            "transaction_concession": concession,
            "observation_noise": noise,
            "large_print_threshold": threshold,
            "is_large_print": bool(is_large),
            "source_leader_event_id": event_id if "leader_follower" in planted_ids else None,
            "planted_effect_ids": ",".join(planted_ids),
        }
        return public, truth
