from __future__ import annotations

import pandas as pd

from bondalpha.features.leader_follower import compute


def test_leader_follower_uses_prior_leader_activity_only() -> None:
    frame = _issuer_frame()
    signal = compute(frame, half_life_events=100.0)

    leader_rows = frame["synthetic_bond_id"].eq("B0")
    follower_rows = frame["synthetic_bond_id"].eq("B1")

    assert signal.loc[leader_rows].eq(0.0).all()
    assert signal.loc[follower_rows].iloc[0] > 0.0


def test_future_events_do_not_change_historical_leadlag_signal() -> None:
    frame = _issuer_frame()
    cutoff = pd.Timestamp("2026-01-01 10:20", tz="UTC")
    base = compute(frame)
    extended = pd.concat(
        [
            frame,
            pd.DataFrame(
                [
                    {
                        "scenario": "controlled_all",
                        "synthetic_issuer_id": "I0",
                        "synthetic_bond_id": "B9",
                        "event_id": "future-heavy-1",
                        "timestamp_utc": pd.Timestamp("2026-01-01 11:00", tz="UTC"),
                        "side": -1,
                        "notional": 10_000_000.0,
                    },
                    {
                        "scenario": "controlled_all",
                        "synthetic_issuer_id": "I0",
                        "synthetic_bond_id": "B9",
                        "event_id": "future-heavy-2",
                        "timestamp_utc": pd.Timestamp("2026-01-01 11:10", tz="UTC"),
                        "side": -1,
                        "notional": 10_000_000.0,
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    extended_signal = compute(extended)
    historical = pd.to_datetime(frame["timestamp_utc"], utc=True) <= cutoff

    pd.testing.assert_series_equal(
        base.loc[historical].reset_index(drop=True),
        extended_signal.iloc[: len(frame)].loc[historical.to_numpy()].reset_index(drop=True),
    )


def test_leader_follower_is_time_ordered_not_input_ordered() -> None:
    frame = _issuer_frame()
    shuffled = frame.sample(frac=1.0, random_state=7).reset_index(drop=True)
    ordered_signal = compute(frame)
    shuffled_signal = compute(shuffled)
    merged = frame[["event_id"]].assign(signal=ordered_signal).merge(
        shuffled[["event_id"]].assign(signal=shuffled_signal),
        on="event_id",
        suffixes=("_ordered", "_shuffled"),
    )

    assert (merged["signal_ordered"] == merged["signal_shuffled"]).all()


def _issuer_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            _row("e0", "B0", "2026-01-01 09:30", 1, 1_000_000.0),
            _row("e1", "B0", "2026-01-01 09:40", 1, 1_000_000.0),
            _row("e2", "B0", "2026-01-01 09:50", 1, 1_000_000.0),
            _row("e3", "B1", "2026-01-01 10:00", -1, 500_000.0),
            _row("e4", "B0", "2026-01-01 10:10", -1, 1_000_000.0),
            _row("e5", "B1", "2026-01-01 10:20", 1, 500_000.0),
        ]
    )


def _row(event_id: str, bond_id: str, timestamp: str, side: int, notional: float) -> dict[str, object]:
    return {
        "scenario": "controlled_all",
        "synthetic_issuer_id": "I0",
        "synthetic_bond_id": bond_id,
        "event_id": event_id,
        "timestamp_utc": pd.Timestamp(timestamp, tz="UTC"),
        "side": side,
        "notional": notional,
    }
