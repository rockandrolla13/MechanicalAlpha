from pathlib import Path

import pandas as pd
import pytest

from bondsim.calendar import assign_session_dates, assert_no_weekend_sessions, build_session_calendar
from bondsim.outputs import assert_public_schema_is_clean, monthly_partition_path, partition_frame_by_month
from bondsim.validation.recovery import (
    leadlag_recovery,
    reversal_recovery,
    run_oracle_accounting_checks,
    run_public_recovery_checks,
    run_recovery_checks,
    sign_persistence_recovery,
)


def test_session_calendar_skips_weekends_and_holidays() -> None:
    calendar = build_session_calendar("2026-01-02", 3, holidays=["2026-01-05"])
    assert [str(day.date()) for day in calendar.sessions] == ["2026-01-02", "2026-01-06", "2026-01-07"]
    assert_no_weekend_sessions(calendar.sessions)


def test_assign_session_dates_and_month_partitions() -> None:
    frame = pd.DataFrame(
        {
            "event_id": ["a", "b"],
            "timestamp_utc": ["2026-01-30 15:00:00+00:00", "2026-02-02 15:00:00+00:00"],
        }
    )
    with_sessions = assign_session_dates(frame)
    assert with_sessions["session_date"].tolist() == ["2026-01-30", "2026-02-02"]
    partitions = partition_frame_by_month(frame, root=Path("data"), dataset="trades")
    assert [(spec.year, spec.month, spec.rows) for spec, _ in partitions] == [(2026, 1, 1), (2026, 2, 1)]
    assert monthly_partition_path(Path("root"), "trades", 2026, 2).as_posix().endswith(
        "root/trades/year=2026/month=02/part-0000.parquet"
    )


def test_public_schema_rejects_truth_columns() -> None:
    assert_public_schema_is_clean(["event_id", "price"])
    with pytest.raises(ValueError, match="forbidden"):
        assert_public_schema_is_clean(["event_id", "planted_large_print_state"])


def test_recovery_checks_on_hand_built_fixture() -> None:
    public, truth = _fixture()
    report = run_recovery_checks(public, truth, horizon="1h")
    by_name = {row["name"]: row for row in report["results"]}
    assert by_name["reversal"]["passed"]
    assert by_name["sign_persistence"]["passed"]
    assert by_name["leadlag"]["passed"]


def test_individual_recovery_failures_are_explicit() -> None:
    public, truth = _fixture()
    no_truth = truth.assign(planted_effect_ids="")
    assert not reversal_recovery(public, no_truth, pd.Timedelta("1h")).passed
    assert sign_persistence_recovery(public).n > 0
    assert not leadlag_recovery(public, no_truth, pd.Timedelta("1h")).passed


def test_public_recovery_and_oracle_accounting() -> None:
    public, truth = _fixture()
    report = run_public_recovery_checks(public, horizon="1h")
    by_name = {row["name"]: row for row in report["results"]}
    assert by_name["public_reversal"]["passed"]
    assert by_name["public_leader_to_follower"]["passed"]
    rich_truth = truth.assign(
        scenario="controlled_all",
        timestamp_utc=public["timestamp_utc"],
        session_date=public["session_date"],
        latent_fair_value=100.0,
        ou_pressure=0.0,
        permanent_impact_state=0.0,
        ordinary_temporary_impact_state=0.0,
        planted_large_print_state=[0.1, 0, 0, 0, 0, 0, 0],
        planted_leadlag_state=[0.2, 0, 0, 0, 0, 0, 0],
        latent_mid_without_planted_effects=100.0,
        latent_mid_with_planted_effects=[100.3, 100, 100, 100, 100, 100, 100],
        transaction_concession=0.0,
        observation_noise=0.0,
    )
    assert run_oracle_accounting_checks(rich_truth)["passed"]


def _fixture() -> tuple[pd.DataFrame, pd.DataFrame]:
    public = pd.DataFrame(
        [
            _trade("e1", "2026-01-05 10:00:00+00:00", "SB1", "SI1", 1, 100.00),
            _trade("e2", "2026-01-05 10:10:00+00:00", "SB1", "SI1", 1, 99.95),
            _trade("e3", "2026-01-05 11:05:00+00:00", "SB1", "SI1", 1, 99.80),
            _trade("e4", "2026-01-05 10:05:00+00:00", "SB2", "SI1", 1, 100.20),
            _trade("e5", "2026-01-05 10:30:00+00:00", "SB2", "SI1", 1, 100.30),
            _trade("e6", "2026-01-05 10:20:00+00:00", "SB3", "SI2", -1, 101.00),
            _trade("e7", "2026-01-05 10:40:00+00:00", "SB3", "SI2", -1, 100.90),
        ]
    )
    truth = pd.DataFrame(
        {
            "event_id": ["e1", "e2", "e3", "e4", "e5", "e6", "e7"],
            "planted_effect_ids": ["large_print_reversal,leader_follower", "", "", "", "", "", ""],
        }
    )
    return public, truth


def _trade(event_id: str, timestamp: str, bond: str, issuer: str, side: int, price: float) -> dict[str, object]:
    return {
        "event_id": event_id,
        "timestamp_utc": timestamp,
        "session_date": timestamp[:10],
        "synthetic_bond_id": bond,
        "synthetic_issuer_id": issuer,
        "side": side,
        "notional": 1_000_000.0,
        "price": price,
        "is_interdealer": False,
        "trade_type": "customer",
        "venue_bucket": "synthetic",
        "reporting_delay_ms": 0.0,
        "currency": "USD",
    }
