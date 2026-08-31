from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from bondalpha.access_control import require_public_columns, require_public_dataset_path
from bondalpha.schemas import MarketDataSchema, TargetSchema
from bondalpha.target_labels import build_target_labels


def test_public_access_control_rejects_truth_paths_and_columns() -> None:
    with pytest.raises(PermissionError):
        require_public_dataset_path(Path("data/quarantine/gate4_truth/run"))
    with pytest.raises(PermissionError):
        require_public_columns(["event_id", "planted_large_print_state"])


def test_schema_names_keep_targets_separate() -> None:
    assert "side" in MarketDataSchema().required_columns
    targets = TargetSchema().target_types
    assert "future_clean_price_move" in targets
    assert "future_issuer_residual_move" in targets
    assert "next_event_side" in targets
    assert "future_signed_flow" in targets


def test_target_labels_are_separate_public_observable_targets() -> None:
    frame = pd.DataFrame(
        {
            "scenario": ["controlled_all"] * 4,
            "synthetic_bond_id": ["B1"] * 4,
            "synthetic_issuer_id": ["I1"] * 4,
            "event_id": ["e1", "e2", "e3", "e4"],
            "timestamp_utc": pd.date_range("2026-01-01 09:30", periods=4, freq="30min", tz="UTC"),
            "session_date": ["2026-01-01"] * 4,
            "side": [1, -1, 1, -1],
            "notional": [100.0, 200.0, 300.0, 400.0],
            "price": [100.0, 100.1, 100.0, 100.2],
        }
    )
    labeled = build_target_labels(frame, ["30m"])
    assert labeled.loc[0, "future_clean_price_move_30m"] == pytest.approx(0.1)
    assert labeled.loc[0, "next_event_side"] == -1
    assert labeled.loc[0, "future_signed_flow_30m"] == pytest.approx(-200.0)
    assert "future_issuer_residual_move_30m" in labeled.columns
