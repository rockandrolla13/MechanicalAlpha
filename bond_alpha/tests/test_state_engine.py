import pandas as pd
import pytest

from mechanical_alpha.state_engine import (
    ClockType,
    FeatureSpec,
    MarketEvent,
    PointInTimeStateEngine,
    WindowSpec,
)


def _ts(value: str) -> pd.Timestamp:
    return pd.Timestamp(value)


def _features() -> list[FeatureSpec]:
    return [
        FeatureSpec(
            name="rfq_count_last_5",
            window=WindowSpec("last_5_rfqs", ClockType.RFQ_EVENT, 5),
            operator="count",
            value_field=None,
        ),
        FeatureSpec(
            name="trade_signed_notional_30m",
            window=WindowSpec("trade_30m", ClockType.CALENDAR, pd.Timedelta(minutes=30), event_types=("trace_trade",)),
            operator="signed_sum",
            value_field="notional",
        ),
        FeatureSpec(
            name="trade_vwap_last_5",
            window=WindowSpec("last_5_trades", ClockType.TRADE_EVENT, 5),
            operator="vwap",
            value_field="price",
            weight_field="notional",
        ),
        FeatureSpec(
            name="notional_count_1mm",
            window=WindowSpec("notional_1mm", ClockType.NOTIONAL, 1_000_000.0, event_types=("trace_trade",)),
            operator="count",
            value_field=None,
        ),
        FeatureSpec(
            name="composite_last_change",
            window=WindowSpec("last_composite", ClockType.COMPOSITE_UPDATE, 1),
            operator="last",
            value_field="price",
        ),
    ]


def _base_events() -> list[MarketEvent]:
    return [
        MarketEvent(
            event_id="rfq-1",
            source="rfq",
            event_type="rfq_inquiry",
            timestamp=_ts("2026-01-02 09:00"),
            effective_time=_ts("2026-01-02 09:00"),
            bond_id="B1",
            issuer_id="I1",
            side=1,
            notional=500_000.0,
            sequence=1,
        ),
        MarketEvent(
            event_id="rfq-2",
            source="rfq",
            event_type="rfq_inquiry",
            timestamp=_ts("2026-01-02 09:00"),
            effective_time=_ts("2026-01-02 09:00"),
            bond_id="B1",
            issuer_id="I1",
            side=-1,
            notional=250_000.0,
            sequence=2,
        ),
        MarketEvent(
            event_id="tr-1",
            source="trace",
            event_type="trace_trade",
            timestamp=_ts("2026-01-02 09:05"),
            effective_time=_ts("2026-01-02 09:05"),
            publication_time=_ts("2026-01-02 09:20"),
            bond_id="B1",
            issuer_id="I1",
            side=1,
            notional=400_000.0,
            price=100.0,
            sequence=3,
        ),
        MarketEvent(
            event_id="tr-2",
            source="trace",
            event_type="trace_trade",
            timestamp=_ts("2026-01-02 09:10"),
            effective_time=_ts("2026-01-02 09:10"),
            publication_time=_ts("2026-01-02 09:12"),
            bond_id="B1",
            issuer_id="I1",
            side=-1,
            notional=700_000.0,
            price=101.0,
            sequence=4,
        ),
        MarketEvent(
            event_id="cmp-1",
            source="composite",
            event_type="composite_snapshot",
            timestamp=_ts("2026-01-02 09:15"),
            effective_time=_ts("2026-01-02 09:15"),
            revision_time=_ts("2026-01-02 10:00"),
            bond_id="B1",
            issuer_id="I1",
            price=100.5,
            sequence=5,
        ),
    ]


def _value(frame: pd.DataFrame, feature: str) -> object:
    row = frame.loc[frame["feature_name"] == feature].iloc[0]
    return row["value"]


def test_simultaneous_events_and_multi_clock_outputs() -> None:
    frame = PointInTimeStateEngine.replay_batch(_base_events(), _features(), [_ts("2026-01-02 09:30")], keys=["B1"])

    assert _value(frame, "rfq_count_last_5") == 2
    assert _value(frame, "trade_signed_notional_30m") == -300_000.0
    assert _value(frame, "trade_vwap_last_5") == pytest.approx((100.0 * 400_000 + 101.0 * 700_000) / 1_100_000)
    assert _value(frame, "notional_count_1mm") == 2
    assert _value(frame, "composite_last_change") == 100.5


def test_no_trades_distinct_from_zero_and_staleness_flag() -> None:
    engine = PointInTimeStateEngine(
        [FeatureSpec("sum_5m", WindowSpec("trade_5m", ClockType.CALENDAR, pd.Timedelta(minutes=5), ("trace_trade",)), "sum")],
        stale_after=pd.Timedelta(minutes=1),
    )
    frame = engine.to_frame(_ts("2026-01-02 09:30"), keys=["B1"])

    assert frame.iloc[0]["value"] is None
    assert frame.iloc[0]["observation_count"] == 0
    assert "no_observations" in frame.iloc[0]["quality_flags"]


def test_duplicate_policy_keeps_first_message() -> None:
    duplicate = MarketEvent(
        event_id="tr-1",
        source="trace",
        event_type="trace_trade",
        timestamp=_ts("2026-01-02 09:25"),
        effective_time=_ts("2026-01-02 09:25"),
        bond_id="B1",
        issuer_id="I1",
        side=1,
        notional=9_000_000.0,
        price=99.0,
    )
    frame = PointInTimeStateEngine.replay_batch(
        _base_events() + [duplicate],
        _features(),
        [_ts("2026-01-02 09:30")],
        keys=["B1"],
        duplicate_policy="keep_first",
    )

    assert _value(frame, "trade_signed_notional_30m") == -300_000.0


def test_cancellation_and_correction_are_point_in_time() -> None:
    features = [
        FeatureSpec(
            "last_composite",
            WindowSpec("last_cmp", ClockType.COMPOSITE_UPDATE, 1),
            "last",
            value_field="price",
        )
    ]
    correction = MarketEvent(
        event_id="cmp-2",
        source="composite",
        event_type="composite_snapshot",
        timestamp=_ts("2026-01-02 10:00"),
        effective_time=_ts("2026-01-02 10:00"),
        bond_id="B1",
        issuer_id="I1",
        price=100.8,
        action="correction",
        corrected_event_id="cmp-1",
    )
    before = PointInTimeStateEngine.replay_batch(_base_events() + [correction], features, [_ts("2026-01-02 09:30")], keys=["B1"])
    after = PointInTimeStateEngine.replay_batch(_base_events() + [correction], features, [_ts("2026-01-02 10:01")], keys=["B1"])

    assert _value(before, "last_composite") == 100.5
    assert _value(after, "last_composite") == 100.8

    cancel = MarketEvent(
        event_id="cancel-cmp-2",
        source="composite",
        event_type="composite_snapshot",
        timestamp=_ts("2026-01-02 10:05"),
        effective_time=_ts("2026-01-02 10:05"),
        bond_id="B1",
        issuer_id="I1",
        action="cancel",
        corrected_event_id="cmp-2",
    )
    cancelled = PointInTimeStateEngine.replay_batch(
        _base_events() + [correction, cancel],
        features,
        [_ts("2026-01-02 10:06")],
        keys=["B1"],
    )

    assert _value(cancelled, "last_composite") is None


def test_late_trace_report_uses_publication_time_when_configured() -> None:
    feature = [FeatureSpec("trace_count", WindowSpec("trace", ClockType.TRADE_EVENT, 5), "count", value_field=None)]
    before = PointInTimeStateEngine.replay_batch(
        _base_events(),
        feature,
        [_ts("2026-01-02 09:15")],
        keys=["B1"],
        timestamp_policy="publication",
    )
    after = PointInTimeStateEngine.replay_batch(
        _base_events(),
        feature,
        [_ts("2026-01-02 09:21")],
        keys=["B1"],
        timestamp_policy="publication",
    )

    assert _value(before, "trace_count") == 1
    assert _value(after, "trace_count") == 2


def test_out_of_order_reject_policy_raises() -> None:
    engine = PointInTimeStateEngine(_features(), out_of_order_policy="reject")
    engine.update(_base_events()[2])

    with pytest.raises(ValueError, match="out-of-order"):
        engine.update(_base_events()[0])


def test_crossing_midnight_weekend_and_holiday_calendar_window() -> None:
    feature = [FeatureSpec("calendar_count", WindowSpec("one_business_day", ClockType.CALENDAR, pd.Timedelta(days=1)), "count")]
    events = [
        MarketEvent("fri", "rfq", "rfq_inquiry", _ts("2026-01-02 16:00"), "B1", effective_time=_ts("2026-01-02 16:00")),
        MarketEvent("mon", "rfq", "rfq_inquiry", _ts("2026-01-05 09:00"), "B1", effective_time=_ts("2026-01-05 09:00")),
        MarketEvent("tue", "rfq", "rfq_inquiry", _ts("2026-01-06 09:00"), "B1", effective_time=_ts("2026-01-06 09:00")),
    ]
    frame = PointInTimeStateEngine.replay_batch(
        events,
        feature,
        [_ts("2026-01-06 10:00")],
        keys=["B1"],
        holidays=[_ts("2026-01-05")],
    )

    assert _value(frame, "calendar_count") == 1


def test_universe_entry_and_exit_flags() -> None:
    feature = [FeatureSpec("rfq_count", WindowSpec("rfq", ClockType.RFQ_EVENT, 5), "count", value_field=None)]
    events = [
        MarketEvent(
            "entry",
            "rfq",
            "rfq_inquiry",
            _ts("2026-01-03 10:00"),
            "B2",
            effective_time=_ts("2026-01-03 10:00"),
            active_from=_ts("2026-01-03"),
            active_until=_ts("2026-01-05"),
        )
    ]

    before = PointInTimeStateEngine.replay_batch(events, feature, [_ts("2026-01-02 10:00")], keys=["B2"])
    during = PointInTimeStateEngine.replay_batch(events, feature, [_ts("2026-01-03 11:00")], keys=["B2"])
    after = PointInTimeStateEngine.replay_batch(events, feature, [_ts("2026-01-05 10:00")], keys=["B2"])

    assert "outside_universe" in before.iloc[0]["quality_flags"]
    assert "outside_universe" not in during.iloc[0]["quality_flags"]
    assert "outside_universe" in after.iloc[0]["quality_flags"]


def test_batch_and_streaming_outputs_are_identical() -> None:
    events = list(reversed(_base_events()))
    asofs = [_ts("2026-01-02 09:10"), _ts("2026-01-02 09:30")]
    batch = PointInTimeStateEngine.replay_batch(events, _features(), asofs, keys=["B1"])
    online = PointInTimeStateEngine.replay_online(events, _features(), asofs, keys=["B1"])

    pd.testing.assert_frame_equal(
        batch.sort_values(["as_of", "feature_name"]).reset_index(drop=True),
        online.sort_values(["as_of", "feature_name"]).reset_index(drop=True),
    )
