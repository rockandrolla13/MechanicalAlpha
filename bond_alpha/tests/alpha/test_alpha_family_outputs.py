from __future__ import annotations

from datetime import date

from bondalpha.composite import build_composite_scaffold
from bondalpha.flow import build_flow_persistence_family
from bondalpha.leadlag import build_lead_lag_family
from bondalpha.relative_value import build_relative_value_family
from bondalpha.reversal import build_reversal_family


def _sample_rows() -> list[dict[str, object]]:
    return [
        {"date": date(2026, 8, 31), "asset_id": "bond-a", "price_return": -0.02, "turnover": 4.0, "net_flow": 1.2, "trade_count": 12, "equity_move": 0.015, "credit_move": -0.002, "etf_move": 0.010, "cash_move": 0.003, "spread": 180.0, "sector": "energy"},
        {"date": date(2026, 8, 31), "asset_id": "bond-b", "price_return": 0.01, "turnover": 9.0, "net_flow": -0.6, "trade_count": 8, "equity_move": -0.010, "credit_move": 0.004, "etf_move": -0.012, "cash_move": -0.001, "spread": 160.0, "sector": "energy"},
        {"date": date(2026, 8, 31), "asset_id": "bond-c", "price_return": -0.005, "turnover": 6.0, "net_flow": 0.3, "trade_count": 6, "equity_move": 0.005, "credit_move": 0.002, "etf_move": 0.001, "cash_move": 0.003, "spread": 220.0, "sector": "utilities"},
    ]


def test_alpha_family_outputs_are_standalone_and_composable() -> None:
    rows = _sample_rows()
    outputs = [
        *build_reversal_family(rows),
        *build_flow_persistence_family(rows),
        *build_lead_lag_family(rows),
        *build_relative_value_family(rows),
    ]
    assert len(outputs) == 12
    assert all(output["alpha_name"] for output in outputs)
    assert all(isinstance(output["metadata"], dict) for output in outputs)
    assert all(-3.0 <= float(output["score"]) <= 3.0 for output in outputs)
    composite = build_composite_scaffold(outputs, selection_size=2)
    assert len(composite["candidates"]) == 2
    assert all(row["alpha_family"] == "composite" for row in composite["candidates"])
