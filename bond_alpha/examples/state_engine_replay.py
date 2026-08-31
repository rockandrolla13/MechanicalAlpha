"""Small deterministic replay example for one corporate bond."""

from __future__ import annotations

import pandas as pd

from mechanical_alpha.state_engine import ClockType, FeatureSpec, MarketEvent, PointInTimeStateEngine, WindowSpec


def main() -> None:
    events = [
        MarketEvent(
            event_id="rfq-1",
            source="rfq",
            event_type="rfq_inquiry",
            timestamp=pd.Timestamp("2026-01-02 09:00"),
            effective_time=pd.Timestamp("2026-01-02 09:00"),
            bond_id="BOND-1",
            issuer_id="ISSUER-1",
            side=1,
            notional=1_000_000.0,
        ),
        MarketEvent(
            event_id="trade-1",
            source="trace",
            event_type="trace_trade",
            timestamp=pd.Timestamp("2026-01-02 09:10"),
            effective_time=pd.Timestamp("2026-01-02 09:10"),
            publication_time=pd.Timestamp("2026-01-02 09:25"),
            bond_id="BOND-1",
            issuer_id="ISSUER-1",
            side=-1,
            notional=500_000.0,
            price=100.25,
        ),
        MarketEvent(
            event_id="composite-1",
            source="composite",
            event_type="composite_snapshot",
            timestamp=pd.Timestamp("2026-01-02 09:15"),
            effective_time=pd.Timestamp("2026-01-02 09:15"),
            bond_id="BOND-1",
            issuer_id="ISSUER-1",
            price=100.10,
        ),
    ]
    features = [
        FeatureSpec("last_5_rfq_count", WindowSpec("last_5_rfqs", ClockType.RFQ_EVENT, 5), "count", value_field=None),
        FeatureSpec(
            "trade_30m_signed_notional",
            WindowSpec("trade_30m", ClockType.CALENDAR, pd.Timedelta(minutes=30), event_types=("trace_trade",)),
            "signed_sum",
            value_field="notional",
        ),
        FeatureSpec(
            "last_composite_mid",
            WindowSpec("last_composite", ClockType.COMPOSITE_UPDATE, 1),
            "last",
            value_field="price",
        ),
    ]
    frame = PointInTimeStateEngine.replay_batch(
        events,
        features,
        [pd.Timestamp("2026-01-02 09:30")],
        keys=["BOND-1"],
    )
    print(frame[["key", "as_of", "feature_name", "value", "observation_count", "quality_flags"]].to_string(index=False))


if __name__ == "__main__":
    main()
