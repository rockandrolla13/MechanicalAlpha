from pathlib import Path

import pandas as pd
import pytest

from mechanical_alpha.availability import evaluate_registry
from mechanical_alpha.contracts import FieldStatus, SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.data.synthetic import load_synthetic_bundle
from mechanical_alpha.registry import default_registry
from mechanical_alpha.schema import Availability, SideConvention


def _metadata() -> SourceMetadata:
    return SourceMetadata(
        name="fixture",
        side_convention=SideConvention.DEALER,
        side_semantics="fixture side is dealer perspective",
        price_units="par price",
        size_units="par amount",
        point_in_time_safety="fixture",
    )


def _events() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_id": ["e1", "e2"],
            "prediction_timestamp": pd.to_datetime(["2026-01-02 10:00", "2026-01-02 11:00"]),
            "bond_id": ["b1", "b1"],
            "issuer_id": ["i1", "i1"],
            "side": [1, -1],
            "price": [100.1, 100.0],
            "notional": [1_000_000.0, 500_000.0],
        }
    )


def test_bundle_validates_public_schema() -> None:
    bundle = bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]}),
        events=_events(),
        metadata=_metadata(),
    )

    assert bundle.events["side"].tolist() == [1, -1]
    assert set(bundle.public_tables()) == {"bonds", "events"}


def test_bundle_rejects_truth_and_source_identifier_columns() -> None:
    events = _events()
    events["latent_fair_value"] = 100.0

    with pytest.raises(ValueError, match="forbidden public columns"):
        bundle_from_frames(
            bonds=pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]}),
            events=events,
            metadata=_metadata(),
        )


def test_availability_registry_marks_trace_side_as_ambiguous() -> None:
    bundle = bundle_from_frames(
        bonds=pd.DataFrame({"bond_id": ["b1"], "issuer_id": ["i1"]}),
        events=_events(),
        metadata=_metadata(),
        availability={
            "side": FieldStatus("side", Availability.AMBIGUOUS, "rpt_side_cd"),
            "notional": FieldStatus("notional", Availability.AMBIGUOUS, "entrd_vol_qt"),
        },
    )

    capabilities = {item.factor_id: item for item in evaluate_registry(bundle, default_registry())}
    assert capabilities["B1"].availability == Availability.AMBIGUOUS
    assert capabilities["B3"].availability == Availability.AMBIGUOUS
    assert capabilities["B9"].availability == Availability.AMBIGUOUS


def test_synthetic_adapter_does_not_read_truth(tmp_path: Path) -> None:
    scenario_root = tmp_path / "scenario=controlled_all"
    trades_root = scenario_root / "trades" / "year=2026" / "month=01"
    trades_root.mkdir(parents=True)
    pd.DataFrame(
        {
            "synthetic_bond_id": ["sb1"],
            "synthetic_issuer_id": ["si1"],
            "liquidity_bucket": ["high"],
        }
    ).to_parquet(scenario_root / "bonds.parquet", index=False)
    pd.DataFrame(
        {
            "event_id": ["e1"],
            "timestamp_utc": ["2026-01-02 10:00:00"],
            "session_date": ["2026-01-02"],
            "synthetic_bond_id": ["sb1"],
            "synthetic_issuer_id": ["si1"],
            "side": [1],
            "notional": [1000000.0],
            "price": [100.0],
            "is_interdealer": [False],
            "truth_label": ["must_not_leak"],
        }
    ).drop(columns=["truth_label"]).to_parquet(trades_root / "part-0000.parquet", index=False)
    truth_root = tmp_path / "synthetic_truth" / "scenario=controlled_all" / "event_truth" / "year=2026" / "month=01"
    truth_root.mkdir(parents=True)
    pd.DataFrame({"event_id": ["e1"], "latent_fair_value": [99.9]}).to_parquet(
        truth_root / "part-0000.parquet", index=False
    )

    bundle = load_synthetic_bundle(scenario_root)

    assert "latent_fair_value" not in bundle.events.columns
    assert "source_bond_id" not in bundle.bonds.columns
    assert bundle.events["bond_id"].tolist() == ["sb1"]

