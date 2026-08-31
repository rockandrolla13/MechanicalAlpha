"""Canonical TRACE preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from bondsim.config import BondSimConfig
from bondsim.io import write_parquet


@dataclass(frozen=True)
class PreparedDataManifest:
    bonds_path: Path
    events_path: Path
    split_dates: dict[str, tuple[str, str]]
    rows: dict[str, int]


def prepare_data(config: BondSimConfig, mode: str = "full") -> PreparedDataManifest:
    mapping = _resolved_mapping(config)
    events = _load_marketdb_events(mapping, limit=250000 if mode == "smoke" else None)
    events = add_event_features(events, config.activity.intraday_bucket_minutes)
    split_dates = temporal_split(events, config)
    events = assign_split(events, split_dates)
    bonds = build_bonds(events)
    root = config.paths.processed_root
    bonds_path = write_parquet(bonds, root / "bonds.parquet", config.simulation.parquet_compression)
    events_path = write_parquet(events, root / "events.parquet", config.simulation.parquet_compression)
    return PreparedDataManifest(
        bonds_path=bonds_path,
        events_path=events_path,
        split_dates=split_dates,
        rows={"bonds": len(bonds), "events": len(events)},
    )


def _resolved_mapping(config: BondSimConfig) -> dict[str, str | None]:
    """Load resolved canonical column mappings, falling back to config columns."""

    candidates = [
        Path("configs/column_mapping.generated.yaml"),
        Path("bond_alpha/configs/column_mapping.generated.yaml"),
    ]
    for path in candidates:
        if path.exists():
            raw = yaml.safe_load(path.read_text()) or {}
            columns = raw.get("columns", {})
            if columns:
                return columns
    return {key: (None if value == "auto" else value) for key, value in config.columns.items()}


def _load_marketdb_events(mapping: dict[str, str | None], limit: int | None = None) -> pd.DataFrame:
    import marketdb

    con = marketdb.connect()
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    timestamp = mapping.get("timestamp") or "trd_exctn_ts"
    bond_id = mapping.get("bond_id") or "cusip"
    issuer_id = mapping.get("issuer_id") or "company_symbol"
    side = mapping.get("side") or "rpt_side_cd"
    price = mapping.get("price") or "rptd_pr"
    notional = mapping.get("notional") or "entrd_vol_qt"
    is_interdealer = mapping.get("is_interdealer") or "cntra_mp_id"
    trade_type = mapping.get("trade_type") or is_interdealer
    yield_col = mapping.get("yield") or "yld_pt"
    query = f"""
        SELECT
            row_number() OVER (ORDER BY {timestamp}, {bond_id}, {price}, {notional}) AS event_id,
            {timestamp} AS timestamp_utc,
            CAST({timestamp} AS DATE) AS session_date,
            {bond_id} AS source_bond_id,
            {issuer_id} AS source_issuer_id,
            CASE WHEN {side} = 'B' THEN 1 WHEN {side} = 'S' THEN -1 ELSE NULL END AS side,
            {price} AS price,
            {notional} AS notional,
            {is_interdealer} = 'D' AS is_interdealer,
            {trade_type} AS trade_type,
            NULL::VARCHAR AS venue,
            NULL::DOUBLE AS reporting_delay_ms,
            NULL::DOUBLE AS bid,
            NULL::DOUBLE AS ask,
            NULL::DOUBLE AS mid,
            NULL::DOUBLE AS fair_value,
            try_cast({yield_col} AS DOUBLE) AS yield,
            NULL::DOUBLE AS oas
        FROM trace
        WHERE {issuer_id} IS NOT NULL
          AND {timestamp} IS NOT NULL
          AND {price} IS NOT NULL
          AND {notional} IS NOT NULL
          AND {side} IN ('B', 'S')
          AND NOT ({is_interdealer}='D' AND {side}='B')
        ORDER BY {timestamp}, {bond_id}
        {limit_sql}
    """
    frame = con.sql(query).df()
    con.close()
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"])
    frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date.astype(str)
    return frame


def add_event_features(events: pd.DataFrame, bucket_minutes: int) -> pd.DataFrame:
    out = events.sort_values(["timestamp_utc", "source_bond_id"], kind="mergesort").reset_index(drop=True)
    ts = pd.to_datetime(out["timestamp_utc"])
    session_open = pd.to_datetime(out["session_date"]) + pd.Timedelta(hours=9, minutes=30)
    seconds = (ts - session_open).dt.total_seconds().clip(lower=0)
    out["seconds_from_session_open"] = seconds
    out["hour_bucket"] = ts.dt.hour.astype(str)
    out["intraday_bucket"] = (seconds // (bucket_minutes * 60)).astype(int)
    out["weekday"] = ts.dt.weekday
    out["log_notional"] = np.log1p(out["notional"].clip(lower=0))
    q90 = out.groupby("source_bond_id")["notional"].transform(lambda s: s.quantile(0.90))
    out["large_print_flag_train"] = out["notional"] >= q90
    out["previous_same_bond_side"] = out.groupby("source_bond_id")["side"].shift(1).fillna(0).astype(int)
    same = out["side"].eq(out["previous_same_bond_side"])
    run_break = (~same).groupby(out["source_bond_id"]).cumsum()
    out["same_side_run_length"] = same.groupby([out["source_bond_id"], run_break]).cumcount() + 1
    out.loc[out["previous_same_bond_side"].eq(0), "same_side_run_length"] = 1
    out["time_since_previous_bond_event_seconds"] = (
        out.groupby("source_bond_id")["timestamp_utc"].diff().dt.total_seconds().fillna(999999999.0)
    )
    out["time_since_previous_issuer_event_seconds"] = (
        out.groupby("source_issuer_id")["timestamp_utc"].diff().dt.total_seconds().fillna(999999999.0)
    )
    signed_notional = out["side"] * out["notional"]
    out["rolling_signed_notional_30m"] = signed_notional.groupby(out["source_bond_id"]).transform(
        lambda s: s.rolling(20, min_periods=1).sum()
    )
    out["rolling_signed_notional_2h"] = signed_notional.groupby(out["source_bond_id"]).transform(
        lambda s: s.rolling(80, min_periods=1).sum()
    )
    daily_counts = out.groupby("session_date")["event_id"].transform("count")
    out["market_activity_regime"] = pd.qcut(daily_counts.rank(method="first"), 3, labels=["quiet", "normal", "busy"])
    bond_counts = out.groupby("source_bond_id")["event_id"].transform("count")
    out["bond_activity_regime"] = pd.qcut(bond_counts.rank(method="first"), 3, labels=["low", "medium", "high"])
    return out


def temporal_split(events: pd.DataFrame, config: BondSimConfig) -> dict[str, tuple[str, str]]:
    sessions = np.array(sorted(events["session_date"].unique()))
    n = len(sessions)
    test_n = min(max(config.split.minimum_test_sessions, int(round(n * config.split.test_fraction))), max(1, n // 3))
    train_n = max(1, int(round(n * config.split.train_fraction)))
    val_n = max(1, n - train_n - test_n)
    if train_n + val_n + test_n > n:
        train_n = n - val_n - test_n
    parts = {
        "train": sessions[:train_n],
        "validation": sessions[train_n : train_n + val_n],
        "test": sessions[train_n + val_n :],
    }
    return {k: (str(v[0]), str(v[-1])) for k, v in parts.items() if len(v)}


def assign_split(events: pd.DataFrame, split_dates: dict[str, tuple[str, str]]) -> pd.DataFrame:
    out = events.copy()
    out["split"] = "unassigned"
    for name, (start, end) in split_dates.items():
        mask = out["session_date"].between(start, end)
        out.loc[mask, "split"] = name
    return out


def build_bonds(events: pd.DataFrame) -> pd.DataFrame:
    active_days = events.groupby("source_bond_id")["session_date"].nunique()
    total_days = events["session_date"].nunique()
    grouped = events.groupby("source_bond_id")
    bonds = grouped.agg(
        source_issuer_id=("source_issuer_id", "first"),
        empirical_events=("event_id", "count"),
        median_notional=("notional", "median"),
        notional_p90=("notional", lambda s: float(s.quantile(0.90))),
    ).reset_index()
    bonds["currency"] = "USD"
    bonds["sector"] = "unknown"
    bonds["industry"] = "unknown"
    bonds["rating"] = "unknown"
    bonds["coupon"] = np.nan
    bonds["maturity_date"] = pd.NaT
    bonds["years_to_maturity"] = np.nan
    bonds["duration"] = np.nan
    bonds["convexity"] = np.nan
    bonds["issue_size"] = np.nan
    bonds["amount_outstanding"] = np.nan
    bonds["seniority"] = "unknown"
    bonds["callable_flag"] = pd.NA
    bonds["benchmark_tenor"] = "unknown"
    bonds["empirical_trades_per_day"] = bonds["source_bond_id"].map(active_days).rdiv(bonds["empirical_events"])
    bonds["zero_trade_day_rate"] = 1.0 - bonds["source_bond_id"].map(active_days) / total_days
    bonds["liquidity_rank_global"] = bonds["empirical_trades_per_day"].rank(method="first", pct=True)
    bonds["liquidity_rank_within_issuer"] = bonds.groupby("source_issuer_id")["empirical_trades_per_day"].rank(
        method="first", pct=True
    )
    bonds["liquidity_bucket"] = pd.qcut(
        bonds["liquidity_rank_global"], 3, labels=["illiquid", "medium", "liquid"]
    ).astype(str)
    bonds["maturity_bucket"] = "unknown"
    bonds["rating_bucket"] = "unknown"
    return bonds.drop(columns=["empirical_events"])
