import math

import numpy as np
import pandas as pd

from mechanical_alpha.pnl_metrics import (
    credit_spread_pnl,
    daily_pnl,
    drawdown,
    gross_exposure,
    mark_to_market_pnl,
    mark_to_market_value,
    max_drawdown,
    max_runup,
    pnl_summary,
    price_trade_pnl,
    profit_factor,
    runup,
    sharpe_like_ratio,
    signed_exposure,
    volatility,
    win_rate,
)


def test_price_trade_pnl_has_hand_calculated_long_and_short_signs() -> None:
    pnl = price_trade_pnl(
        quantity=pd.Series([10.0, -10.0]),
        entry_price=[100.0, 100.0],
        exit_price=[102.0, 98.0],
        cost=[1.0, 1.0],
    )

    assert pnl.tolist() == [19.0, 19.0]


def test_price_trade_pnl_loses_when_price_moves_against_position() -> None:
    pnl = price_trade_pnl(
        quantity=pd.Series([10.0, -10.0]),
        entry_price=100.0,
        exit_price=[98.0, 102.0],
    )

    assert pnl.tolist() == [-20.0, -20.0]


def test_credit_spread_pnl_signs_match_dv01_convention() -> None:
    pnl = credit_spread_pnl(
        quantity=pd.Series([2.0, -2.0]),
        dv01=50.0,
        spread_entry=[100.0, 100.0],
        spread_exit=[95.0, 105.0],
        cost=10.0,
    )

    assert pnl.tolist() == [490.0, 490.0]


def test_credit_spread_pnl_loses_for_long_when_spreads_widen() -> None:
    pnl = credit_spread_pnl(
        quantity=2.0,
        dv01=50.0,
        spread_entry=100.0,
        spread_exit=105.0,
    )

    assert pnl.iloc[0] == -500.0


def test_queue_cash_position_mark_to_market_identity() -> None:
    value = mark_to_market_value(
        cash=pd.Series([1_000.0, 900.0, 1_140.0]),
        position=[0.0, 2.0, -1.0],
        mark_price=[100.0, 105.0, 110.0],
    )
    pnl = mark_to_market_pnl(
        cash=pd.Series([1_000.0, 900.0, 1_140.0]),
        position=[0.0, 2.0, -1.0],
        mark_price=[100.0, 105.0, 110.0],
        starting_value=1_000.0,
    )

    assert value.tolist() == [1_000.0, 1_110.0, 1_030.0]
    assert pnl.tolist() == [0.0, 110.0, 30.0]


def test_daily_pnl_aggregates_event_pnl_by_day() -> None:
    result = daily_pnl(
        pnl=pd.Series([10.0, -3.0, 5.0]),
        timestamps=pd.Series(
            pd.to_datetime(["2026-01-02 10:00", "2026-01-02 15:00", "2026-01-03 09:00"])
        ),
    )

    assert result.index.tolist() == [pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-03")]
    assert result.tolist() == [7.0, 5.0]


def test_signed_and_gross_exposure() -> None:
    signed = signed_exposure(quantity=pd.Series([2.0, -3.0]), mark_price=[101.0, 99.0])
    gross = gross_exposure(quantity=pd.Series([2.0, -3.0]), mark_price=[101.0, 99.0])

    assert signed.tolist() == [202.0, -297.0]
    assert gross.tolist() == [202.0, 297.0]


def test_drawdown_and_runup_are_hand_calculated() -> None:
    equity = pd.Series([100.0, 110.0, 105.0, 120.0, 90.0, 95.0])

    assert drawdown(equity).tolist() == [0.0, 0.0, -5.0, 0.0, -30.0, -25.0]
    assert max_drawdown(equity) == -30.0
    assert runup(equity).tolist() == [0.0, 10.0, 5.0, 20.0, 0.0, 5.0]
    assert max_runup(equity) == 20.0


def test_risk_metrics_are_deterministic() -> None:
    pnl = pd.Series([10.0, -5.0, 0.0, 15.0])

    assert volatility(pnl) == np.std([10.0, -5.0, 0.0, 15.0], ddof=1)
    assert sharpe_like_ratio(pnl) == np.mean([10.0, -5.0, 0.0, 15.0]) / np.std(
        [10.0, -5.0, 0.0, 15.0],
        ddof=1,
    )
    assert profit_factor(pnl) == 5.0
    assert win_rate(pnl) == 2.0 / 3.0
    assert win_rate(pnl, include_zero=True) == 0.5


def test_pnl_summary_includes_requested_metrics() -> None:
    summary = pnl_summary(pd.Series([10.0, -5.0, 15.0]))

    assert summary["count"] == 3.0
    assert summary["total_pnl"] == 20.0
    assert summary["profit_factor"] == 5.0
    assert summary["win_rate"] == 2.0 / 3.0
    assert summary["max_drawdown"] == -5.0
    assert summary["max_runup"] == 15.0
    assert math.isfinite(summary["volatility"])
