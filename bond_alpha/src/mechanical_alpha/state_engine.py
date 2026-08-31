"""Deterministic point-in-time multi-clock state engine."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Literal

import pandas as pd

from mechanical_alpha.operators import OPERATORS, Observation, OperatorResult


class ClockType(str, Enum):
    """Supported independent clocks."""

    CALENDAR = "calendar"
    RFQ_EVENT = "rfq_event"
    TRADE_EVENT = "trade_event"
    NOTIONAL = "notional"
    COMPOSITE_UPDATE = "composite_update"


@dataclass(frozen=True)
class MarketEvent:
    """Canonical event envelope for point-in-time replay.

    Raw source fields stay outside this engine.
    Source adapters map them into this envelope without changing economics.
    """

    event_id: str
    source: str
    event_type: str
    timestamp: pd.Timestamp
    bond_id: str
    issuer_id: str | None = None
    side: int | None = None
    notional: float | None = None
    price: float | None = None
    value: float | None = None
    weight: float | None = None
    effective_time: pd.Timestamp | None = None
    receive_time: pd.Timestamp | None = None
    publication_time: pd.Timestamp | None = None
    revision_time: pd.Timestamp | None = None
    feature_time: pd.Timestamp | None = None
    action: Literal["upsert", "cancel", "correction"] = "upsert"
    corrected_event_id: str | None = None
    sequence: int = 0
    active_from: pd.Timestamp | None = None
    active_until: pd.Timestamp | None = None
    sector: str | None = None
    rating: str | None = None
    is_revision: bool = False
    fields: dict[str, Any] | None = None

    def asof_time(self, policy: Literal["effective", "receive", "publication", "feature"] = "effective") -> pd.Timestamp:
        """Return the timestamp used for point-in-time inclusion."""

        if policy == "receive":
            return self.receive_time or self.timestamp
        if policy == "publication":
            return self.publication_time or self.receive_time or self.timestamp
        if policy == "feature":
            return self.feature_time or self.publication_time or self.receive_time or self.timestamp
        return self.effective_time or self.timestamp

    def numeric_field(self, field: str | None) -> float | None:
        """Read a numeric field from standard attributes or the extra field map."""

        if field is None:
            return None
        if hasattr(self, field):
            value = getattr(self, field)
        elif self.fields and field in self.fields:
            value = self.fields[field]
        else:
            return None
        if value is None:
            return None
        return float(value)


@dataclass(frozen=True)
class WindowSpec:
    """Window definition on one clock."""

    name: str
    clock: ClockType
    size: pd.Timedelta | int | float
    event_types: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    group_scope: Literal["bond", "issuer", "sector", "rating", "market"] = "bond"


@dataclass(frozen=True)
class FeatureSpec:
    """One state feature request."""

    name: str
    window: WindowSpec
    operator: str
    value_field: str | None = "value"
    weight_field: str | None = "weight"
    side_field: str | None = "side"
    x_field: str | None = None
    y_field: str | None = None
    params: dict[str, Any] | None = None


@dataclass(frozen=True)
class StateValue:
    """Point-in-time state output with quality metadata."""

    key: str
    as_of: pd.Timestamp
    feature_name: str
    value: float | int | None
    observation_count: int
    effective_sample_size: float
    last_observation_time: pd.Timestamp | None
    staleness_seconds: float | None
    quality_flags: tuple[str, ...]


class PointInTimeStateEngine:
    """Replay sparse asynchronous market events into deterministic state values."""

    def __init__(
        self,
        feature_specs: Iterable[FeatureSpec],
        *,
        timestamp_policy: Literal["effective", "receive", "publication", "feature"] = "effective",
        out_of_order_policy: Literal["sort", "reject"] = "sort",
        duplicate_policy: Literal["keep_first", "keep_last", "reject"] = "keep_first",
        holidays: Iterable[pd.Timestamp | str] = (),
        stale_after: pd.Timedelta | None = None,
    ) -> None:
        self.feature_specs = tuple(feature_specs)
        self.timestamp_policy = timestamp_policy
        self.out_of_order_policy = out_of_order_policy
        self.duplicate_policy = duplicate_policy
        self.holidays = {pd.Timestamp(day).normalize() for day in holidays}
        self.stale_after = stale_after
        self._records: list[MarketEvent] = []
        self._seen_event_ids: set[str] = set()
        self._max_seen_time: pd.Timestamp | None = None

    def update(self, event: MarketEvent) -> None:
        """Apply one event to online state."""

        event_time = event.asof_time(self.timestamp_policy)
        if self._max_seen_time is not None and event_time < self._max_seen_time:
            if self.out_of_order_policy == "reject":
                raise ValueError(f"out-of-order event {event.event_id}: {event_time} < {self._max_seen_time}")
        self._max_seen_time = max(self._max_seen_time, event_time) if self._max_seen_time is not None else event_time

        if event.event_id in self._seen_event_ids and event.action == "upsert":
            if self.duplicate_policy == "reject":
                raise ValueError(f"duplicate event_id: {event.event_id}")
            if self.duplicate_policy == "keep_first":
                return

        self._seen_event_ids.add(event.event_id)
        self._records.append(event)

    def snapshot(self, as_of: pd.Timestamp, keys: Iterable[str] | None = None) -> list[StateValue]:
        """Compute state values as of one timestamp."""

        as_of = pd.Timestamp(as_of)
        selected_keys = tuple(keys) if keys is not None else self._known_keys(as_of)
        values = []
        for key in selected_keys:
            for spec in self.feature_specs:
                events = self._window_events(spec.window, key, as_of)
                observations = [self._to_observation(event, spec) for event in events]
                result = self._apply_operator(spec, observations, as_of, spec.window)
                flags = list(result.quality_flags)
                if self.stale_after is not None and result.staleness_seconds is not None:
                    if result.staleness_seconds > self.stale_after.total_seconds():
                        flags.append("stale")
                if not self._is_active_key(key, as_of):
                    flags.append("outside_universe")
                values.append(
                    StateValue(
                        key=key,
                        as_of=as_of,
                        feature_name=spec.name,
                        value=result.value,
                        observation_count=result.observation_count,
                        effective_sample_size=result.effective_sample_size,
                        last_observation_time=result.last_observation_time,
                        staleness_seconds=result.staleness_seconds,
                        quality_flags=tuple(dict.fromkeys(flags)),
                    )
                )
        return values

    def to_frame(self, as_of: pd.Timestamp, keys: Iterable[str] | None = None) -> pd.DataFrame:
        """Return a tidy DataFrame of state values."""

        return pd.DataFrame([value.__dict__ for value in self.snapshot(as_of, keys)])

    @classmethod
    def replay_batch(
        cls,
        events: Iterable[MarketEvent],
        feature_specs: Iterable[FeatureSpec],
        as_of_times: Iterable[pd.Timestamp],
        *,
        keys: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Replay all events once, then evaluate requested as-of times.

        This is deterministic and returns the same state as online replay with
        `out_of_order_policy="sort"` because inclusion is controlled by as-of time.
        """

        engine = cls(feature_specs, **kwargs)
        for event in sorted(events, key=lambda item: (item.asof_time(engine.timestamp_policy), item.sequence, item.event_id)):
            engine.update(event)
        frames = [engine.to_frame(pd.Timestamp(as_of), keys) for as_of in as_of_times]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    @classmethod
    def replay_online(
        cls,
        events: Iterable[MarketEvent],
        feature_specs: Iterable[FeatureSpec],
        as_of_times: Iterable[pd.Timestamp],
        *,
        keys: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Replay in arrival order and snapshot at requested times."""

        engine = cls(feature_specs, **kwargs)
        ordered_asofs = sorted(pd.Timestamp(item) for item in as_of_times)
        frames = []
        buffered_events = list(events)
        for event in buffered_events:
            engine.update(event)
        for as_of in ordered_asofs:
            frames.append(engine.to_frame(as_of, keys))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _known_keys(self, as_of: pd.Timestamp) -> tuple[str, ...]:
        keys = {
            event.bond_id
            for event in self._active_events(as_of)
            if self._is_active_key(event.bond_id, as_of)
        }
        return tuple(sorted(keys))

    def _active_events(self, as_of: pd.Timestamp) -> list[MarketEvent]:
        active: dict[str, MarketEvent] = {}
        for event in sorted(self._records, key=lambda item: (item.asof_time(self.timestamp_policy), item.sequence, item.event_id)):
            if event.asof_time(self.timestamp_policy) <= as_of:
                if event.action == "cancel":
                    active.pop(event.corrected_event_id or event.event_id, None)
                elif event.action == "correction":
                    if event.corrected_event_id:
                        active.pop(event.corrected_event_id, None)
                    active[event.event_id] = event
                else:
                    active[event.event_id] = event
        return sorted(active.values(), key=lambda item: (item.asof_time(self.timestamp_policy), item.sequence, item.event_id))

    def _window_events(self, window: WindowSpec, key: str, as_of: pd.Timestamp) -> list[MarketEvent]:
        events = [
            event
            for event in self._active_events(as_of)
            if self._event_matches(window, event, key, as_of)
        ]
        if window.clock == ClockType.CALENDAR:
            start = subtract_business_time(as_of, pd.Timedelta(window.size), self.holidays)
            return [event for event in events if start <= event.asof_time(self.timestamp_policy) <= as_of]
        if window.clock in (ClockType.RFQ_EVENT, ClockType.TRADE_EVENT, ClockType.COMPOSITE_UPDATE):
            return events[-int(window.size) :]
        if window.clock == ClockType.NOTIONAL:
            total = 0.0
            selected = []
            for event in reversed(events):
                selected.append(event)
                total += abs(float(event.notional or 0.0))
                if total >= float(window.size):
                    break
            return list(reversed(selected))
        raise ValueError(f"unsupported clock: {window.clock}")

    def _event_matches(self, window: WindowSpec, event: MarketEvent, key: str, as_of: pd.Timestamp) -> bool:
        if window.event_types and event.event_type not in window.event_types:
            return False
        if window.sources and event.source not in window.sources:
            return False
        if event.active_from is not None and as_of < event.active_from:
            return False
        if event.active_until is not None and as_of >= event.active_until:
            return False
        if window.clock == ClockType.RFQ_EVENT and event.event_type not in {"rfq_inquiry", "rfq_response", "firm_up", "rfq_execution"}:
            return False
        if window.clock == ClockType.TRADE_EVENT and event.event_type not in {"trace_trade", "rfq_execution"}:
            return False
        if window.clock == ClockType.COMPOSITE_UPDATE and event.event_type != "composite_snapshot":
            return False
        if window.group_scope == "market":
            return True
        if window.group_scope == "issuer":
            return event.issuer_id == key or event.bond_id == key
        if window.group_scope == "sector":
            return event.sector == key or (event.fields or {}).get("sector") == key
        if window.group_scope == "rating":
            return event.rating == key or (event.fields or {}).get("rating") == key
        return event.bond_id == key

    def _to_observation(self, event: MarketEvent, spec: FeatureSpec) -> Observation:
        fields = event.fields or {}
        return Observation(
            timestamp=event.asof_time(self.timestamp_policy),
            value=event.numeric_field(spec.value_field) if spec.value_field else event.value,
            side=int(getattr(event, spec.side_field)) if spec.side_field and getattr(event, spec.side_field, None) in (-1, 1) else None,
            weight=event.numeric_field(spec.weight_field) if spec.weight_field else event.weight,
            x=event.numeric_field(spec.x_field) if spec.x_field else None,
            y=event.numeric_field(spec.y_field) if spec.y_field else None,
            baseline_mean=float(fields["baseline_mean"]) if "baseline_mean" in fields else None,
            baseline_std=float(fields["baseline_std"]) if "baseline_std" in fields else None,
            predicted=float(fields["predicted"]) if "predicted" in fields else None,
        )

    def _apply_operator(
        self,
        spec: FeatureSpec,
        observations: list[Observation],
        as_of: pd.Timestamp,
        window: WindowSpec,
    ) -> OperatorResult:
        if spec.operator not in OPERATORS:
            raise ValueError(f"unknown operator: {spec.operator}")
        params = dict(spec.params or {})
        if spec.operator == "intensity":
            params.setdefault("window_seconds", _window_seconds(window))
        return OPERATORS[spec.operator](observations, as_of, **params)

    def _is_active_key(self, key: str, as_of: pd.Timestamp) -> bool:
        key_events = [event for event in self._records if event.bond_id == key]
        if not key_events:
            return True
        starts = [event.active_from for event in key_events if event.active_from is not None]
        ends = [event.active_until for event in key_events if event.active_until is not None]
        if starts and as_of < min(starts):
            return False
        if ends and as_of >= max(ends):
            return False
        return True


def event_from_mapping(row: dict[str, Any]) -> MarketEvent:
    """Create a MarketEvent from a dictionary."""

    converted = dict(row)
    for field in ("timestamp", "effective_time", "receive_time", "publication_time", "revision_time", "feature_time"):
        if converted.get(field) is not None:
            converted[field] = pd.Timestamp(converted[field])
    return MarketEvent(**converted)


def events_from_frame(frame: pd.DataFrame) -> list[MarketEvent]:
    """Create MarketEvent objects from a DataFrame."""

    return [event_from_mapping(row) for row in frame.to_dict("records")]


def subtract_business_time(as_of: pd.Timestamp, delta: pd.Timedelta, holidays: set[pd.Timestamp]) -> pd.Timestamp:
    """Subtract elapsed time while skipping weekend and configured holiday dates."""

    if delta >= pd.Timedelta(days=1) and delta == pd.Timedelta(days=int(delta / pd.Timedelta(days=1))):
        sessions = int(delta / pd.Timedelta(days=1))
        cursor = pd.Timestamp(as_of).normalize()
        counted = 0
        while counted < sessions:
            if is_business_time(cursor, holidays):
                counted += 1
                if counted == sessions:
                    return cursor
            cursor -= pd.Timedelta(days=1)

    remaining = pd.Timedelta(delta)
    cursor = pd.Timestamp(as_of)
    step = pd.Timedelta(minutes=1)
    if remaining <= pd.Timedelta(0):
        return cursor
    while remaining > pd.Timedelta(0):
        cursor -= step
        if is_business_time(cursor, holidays):
            remaining -= step
    return cursor


def is_business_time(timestamp: pd.Timestamp, holidays: set[pd.Timestamp]) -> bool:
    """Return whether a timestamp falls on a business date."""

    day = pd.Timestamp(timestamp).normalize()
    return timestamp.weekday() < 5 and day not in holidays


def with_value(event: MarketEvent, value: float, field: str = "value") -> MarketEvent:
    """Return a copy with a numeric value field set."""

    if field == "value":
        return replace(event, value=value)
    if field == "price":
        return replace(event, price=value)
    fields = dict(event.fields or {})
    fields[field] = value
    return replace(event, fields=fields)
