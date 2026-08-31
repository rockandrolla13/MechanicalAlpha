"""Adapter from local marketdb TRACE to the canonical alpha bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from mechanical_alpha.contracts import AlphaInputBundle, FieldStatus, SourceMetadata
from mechanical_alpha.data.bundle import bundle_from_frames
from mechanical_alpha.schema import Availability, SideConvention


@dataclass(frozen=True)
class TraceAdapterConfig:
    """Configuration for the TRACE marketdb adapter."""

    limit: int | None = None
    filter_interdealer_double_reports: bool = True
    side_convention: SideConvention = SideConvention.CUSTOMER
    side_semantics: str = "TRACE rpt_side_cd mapped as B=customer buy, S=customer sell; verify against source docs before dealer-perspective factors."


def load_marketdb_trace_bundle(connection: Any, config: TraceAdapterConfig | None = None) -> AlphaInputBundle:
    """Load marketdb TRACE rows into the portable alpha contract.

    The adapter receives a connection object.
    It does not create a marketdb connection itself.
    This keeps the alpha package portable to a work-machine adapter.
    """

    cfg = config or TraceAdapterConfig()
    where = "WHERE company_symbol IS NOT NULL"
    if cfg.filter_interdealer_double_reports:
        where += " AND NOT (cntra_mp_id = 'D' AND rpt_side_cd = 'B')"
    limit_sql = "" if cfg.limit is None else f" LIMIT {int(cfg.limit)}"

    events_raw = connection.sql(
        f"""
        SELECT
            cusip,
            company_symbol,
            trd_exctn_ts,
            trd_rpt_dt,
            rptd_pr,
            entrd_vol_qt,
            rpt_side_cd,
            cntra_mp_id,
            try_cast(yld_pt AS DOUBLE) AS yld_pt_numeric
        FROM trace
        {where}
        ORDER BY trd_exctn_ts, cusip
        {limit_sql}
        """
    ).df()

    events = _canonicalize_trace_events(events_raw)
    bonds = _canonicalize_trace_bonds(events)
    availability = _trace_availability()
    metadata = SourceMetadata(
        name="marketdb.trace",
        side_convention=cfg.side_convention,
        side_semantics=cfg.side_semantics,
        price_units="TRACE reported par price. 100 means par.",
        size_units="entrd_vol_qt. Warehouse units are not fully documented.",
        point_in_time_safety="partial: execution timestamp and report date exist; intraday dissemination timestamp is absent.",
        limitations=(
            "15-issuer panel, not broad market TRACE.",
            "No RFQ inquiry/response/firm-up fields.",
            "No bond-level composite bid/ask/mid.",
            "No rating, maturity, sector, duration, or amount outstanding.",
        ),
    )
    return bundle_from_frames(bonds=bonds, events=events, metadata=metadata, availability=availability)


def _canonicalize_trace_events(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    side = frame["rpt_side_cd"].map({"B": 1, "S": -1}).fillna(0).astype(int)
    event_id = pd.util.hash_pandas_object(
        frame[["cusip", "trd_exctn_ts", "rptd_pr", "entrd_vol_qt", "rpt_side_cd", "cntra_mp_id"]].astype(str),
        index=False,
    ).astype(str)
    return pd.DataFrame(
        {
            "event_id": event_id,
            "prediction_timestamp": pd.to_datetime(frame["trd_exctn_ts"]),
            "event_timestamp": pd.to_datetime(frame["trd_exctn_ts"]),
            "publication_timestamp": pd.NaT,
            "revision_timestamp": pd.NaT,
            "session_date": pd.to_datetime(frame["trd_exctn_ts"]).dt.date.astype(str),
            "bond_id": frame["cusip"].astype(str),
            "issuer_id": frame["company_symbol"].astype(str),
            "side": side,
            "price": pd.to_numeric(frame["rptd_pr"]),
            "notional": pd.to_numeric(frame["entrd_vol_qt"]),
            "is_interdealer": frame["cntra_mp_id"].eq("D"),
            "trade_type": frame["cntra_mp_id"].astype(str),
            "yield": pd.to_numeric(frame["yld_pt_numeric"], errors="coerce"),
            "source_table": "marketdb.trace",
        }
    )


def _canonicalize_trace_bonds(events: pd.DataFrame) -> pd.DataFrame:
    grouped = events.groupby("bond_id", as_index=False).agg(
        issuer_id=("issuer_id", "first"),
        first_event=("prediction_timestamp", "min"),
        last_event=("prediction_timestamp", "max"),
        event_count=("event_id", "count"),
        median_notional=("notional", "median"),
    )
    grouped["currency"] = "USD"
    grouped["sector"] = "unknown"
    grouped["rating"] = "unknown"
    grouped["maturity_bucket"] = "unknown"
    grouped["rating_bucket"] = "unknown"
    grouped["liquidity_bucket"] = pd.qcut(
        grouped["event_count"].rank(method="first"),
        q=min(3, len(grouped)),
        labels=["low", "medium", "high"][: min(3, len(grouped))],
        duplicates="drop",
    ).astype(str)
    return grouped


def _trace_availability() -> dict[str, FieldStatus]:
    ambiguous = Availability.AMBIGUOUS
    unavailable = Availability.UNAVAILABLE
    direct = Availability.DIRECT
    derivable = Availability.DERIVABLE
    partial = Availability.PARTIAL
    return {
        "prediction_timestamp": FieldStatus("prediction_timestamp", direct, "trd_exctn_ts"),
        "event_timestamp": FieldStatus("event_timestamp", direct, "trd_exctn_ts"),
        "publication_timestamp": FieldStatus("publication_timestamp", unavailable, None, "Only report date exists."),
        "bond_id": FieldStatus("bond_id", direct, "cusip"),
        "issuer_id": FieldStatus("issuer_id", direct, "company_symbol", "Small missingness filtered by adapter."),
        "side": FieldStatus("side", ambiguous, "rpt_side_cd", "Perspective requires validation."),
        "price": FieldStatus("price", direct, "rptd_pr"),
        "notional": FieldStatus("notional", ambiguous, "entrd_vol_qt", "Units require validation."),
        "is_interdealer": FieldStatus("is_interdealer", derivable, "cntra_mp_id"),
        "yield": FieldStatus("yield", partial, "yld_pt", "String field cast to numeric when possible."),
        "spread": FieldStatus("spread", unavailable),
        "fair_value": FieldStatus("fair_value", unavailable),
        "bid": FieldStatus("bid", unavailable),
        "ask": FieldStatus("ask", unavailable),
        "bid_size": FieldStatus("bid_size", unavailable),
        "ask_size": FieldStatus("ask_size", unavailable),
        "amount_outstanding": FieldStatus("amount_outstanding", unavailable),
        "maturity_date": FieldStatus("maturity_date", unavailable),
        "duration": FieldStatus("duration", unavailable),
        "coupon": FieldStatus("coupon", unavailable),
        "external_factor_value": FieldStatus("external_factor_value", unavailable),
    }

