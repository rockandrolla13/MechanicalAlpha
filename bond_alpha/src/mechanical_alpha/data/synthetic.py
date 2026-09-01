"""Adapter from simulator parquet output to the canonical alpha bundle."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from mechanical_alpha.contracts import AlphaInputBundle
from mechanical_alpha.contracts import FieldStatus, SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.schema import Availability, SideConvention


def load_synthetic_bundle(scenario_root: str | Path) -> AlphaInputBundle:
    """Load public synthetic simulator output as an alpha bundle.

    Truth files are intentionally not read by this adapter.
    """

    root = Path(scenario_root)
    bonds_path = root / "bonds.parquet"
    trade_paths = sorted((root / "trades").glob("year=*/month=*/part-*.parquet"))
    if not bonds_path.exists():
        raise FileNotFoundError(f"missing synthetic bonds file: {bonds_path}")
    if not trade_paths:
        raise FileNotFoundError(f"missing synthetic trade parts under: {root / 'trades'}")

    raw_bonds = pd.read_parquet(bonds_path)
    raw_events = pd.concat([pd.read_parquet(path) for path in trade_paths], ignore_index=True)
    external_factors_path = root / "external_factors.parquet"
    external_factors = pd.read_parquet(external_factors_path) if external_factors_path.exists() else None

    bonds = _canonicalize_synthetic_bonds(raw_bonds)
    events = _canonicalize_synthetic_events(raw_events)
    metadata = SourceMetadata(
        name=f"synthetic:{root.name}",
        side_convention=SideConvention.CUSTOMER,
        side_semantics="Synthetic public side uses BUY=+1 and SELL=-1.",
        price_units="par price points",
        size_units="synthetic notional",
        point_in_time_safety="synthetic public output only; truth tables are excluded.",
        limitations=("Synthetic fields are for test coverage and are not evidence of real-data availability.",),
    )
    availability = {
        "prediction_timestamp": FieldStatus("prediction_timestamp", Availability.DIRECT, "timestamp_utc"),
        "event_timestamp": FieldStatus("event_timestamp", Availability.DIRECT, "timestamp_utc"),
        "bond_id": FieldStatus("bond_id", Availability.DIRECT, "synthetic_bond_id"),
        "issuer_id": FieldStatus("issuer_id", Availability.DIRECT, "synthetic_issuer_id"),
        "side": FieldStatus("side", Availability.DIRECT, "side"),
        "price": FieldStatus("price", Availability.DIRECT, "price"),
        "notional": FieldStatus("notional", Availability.DIRECT, "notional"),
        "is_interdealer": FieldStatus("is_interdealer", Availability.DIRECT, "is_interdealer"),
        "fair_value": FieldStatus("fair_value", Availability.UNAVAILABLE, None, "Public synthetic output excludes latent truth."),
        "spread": FieldStatus("spread", Availability.UNAVAILABLE),
    }
    return bundle_from_frames(
        bonds=bonds,
        events=events,
        metadata=metadata,
        availability=availability,
        external_factors=external_factors,
    )


def _canonicalize_synthetic_bonds(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.rename(columns={"synthetic_bond_id": "bond_id", "synthetic_issuer_id": "issuer_id"}).copy()
    keep = [column for column in frame.columns if column not in {"source_bond_id", "source_issuer_id"}]
    return frame[keep]


def _canonicalize_synthetic_events(raw: pd.DataFrame) -> pd.DataFrame:
    trade_type = raw["trade_type"] if "trade_type" in raw.columns else pd.Series("synthetic", index=raw.index)
    venue = raw["venue_bucket"] if "venue_bucket" in raw.columns else pd.Series("synthetic", index=raw.index)
    frame = pd.DataFrame(
        {
            "event_id": raw["event_id"].astype(str),
            "prediction_timestamp": pd.to_datetime(raw["timestamp_utc"]),
            "event_timestamp": pd.to_datetime(raw["timestamp_utc"]),
            "publication_timestamp": pd.to_datetime(raw["timestamp_utc"]),
            "revision_timestamp": pd.NaT,
            "session_date": raw["session_date"].astype(str),
            "bond_id": raw["synthetic_bond_id"].astype(str),
            "issuer_id": raw["synthetic_issuer_id"].astype(str),
            "side": raw["side"].astype(int),
            "price": pd.to_numeric(raw["price"]),
            "notional": pd.to_numeric(raw["notional"]),
            "is_interdealer": raw["is_interdealer"].astype(bool),
            "trade_type": trade_type.astype(str),
            "venue": venue.astype(str),
        }
    )
    for column in ("dv01", "cr01", "effective_duration", "duration"):
        if column in raw.columns:
            frame[column] = pd.to_numeric(raw[column], errors="coerce")
    return frame
