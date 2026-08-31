"""Corporate-bond tape acquisition.

Public contract:
    load_tape(source) -> DataFrame[cusip, ts, price, par_volume, side_flag, contra_party_type]

The returned tape is trade-time data only. Downstream stages must still enforce as-of joins
when aligning reference data, fair values, and targets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

TAPE_COLUMNS = [
    "cusip",
    "ts",
    "price",
    "par_volume",
    "side_flag",
    "contra_party_type",
]

FINRA_PUBLIC_LIMITATIONS = """
FINRA public TRACE is disseminated transaction data, not the uncapped regulatory tape.
For corporate bonds, investment-grade trades above 5MM par are disseminated as 5MM+.
Non-investment-grade trades above 1MM par are disseminated as 1MM+.
The public tape is useful for price, time, side, count, and capped-volume research.
It is not suitable when exact block size, dealer identifiers, or full regulatory fields are required.
"""


@dataclass(frozen=True)
class SyntheticTapeConfig:
    n_bonds: int = 500
    start: str = "2021-01-01"
    end: str = "2023-12-31"
    seed: int = 7
    median_trades_per_day: float = 2.0
    p10_trades_per_week: float = 2.0
    interdealer_probability: float = 0.08
    reversal_bps_per_log_volume: float = -7.5
    sign_persistence: float = 0.68
    issuer_lead_lag_bps: float = 4.0


def load_tape(source: str | Path | Mapping[str, Any] = "synthetic") -> pd.DataFrame:
    """Load a trade tape from WRDS TRACE, public FINRA TRACE, or synthetic data.

    Parameters
    ----------
    source:
        One of:
        - "synthetic"
        - {"type": "synthetic", ...SyntheticTapeConfig fields}
        - {"type": "finra_public", "path": "...csv"}
        - {"type": "wrds_trace_enhanced", "connection": dbapi_connection, ...}
        - a CSV path, treated as public FINRA-style input
    """

    if isinstance(source, (str, Path)):
        source_text = str(source)
        if source_text == "synthetic":
            return _load_synthetic({})
        return _load_finra_public({"path": source_text})

    source_type = str(source.get("type", "synthetic")).lower()
    if source_type == "synthetic":
        return _load_synthetic(source)
    if source_type in {"finra", "finra_public", "public_trace"}:
        return _load_finra_public(source)
    if source_type in {"wrds", "wrds_trace", "wrds_trace_enhanced"}:
        return _load_wrds_trace_enhanced(source)

    raise ValueError(f"Unsupported tape source type: {source_type!r}")


def _load_wrds_trace_enhanced(source: Mapping[str, Any]) -> pd.DataFrame:
    """Load WRDS TRACE Enhanced joined to configurable FISD reference tables.

    Expected source keys:
        connection: DB-API compatible connection or SQLAlchemy connection.
        start, end: optional date filters.
        universe_sql: optional SQL predicate replacing the UNIVERSE placeholder.
        trace_table: default "trace.trace_enhanced"
        fisd_table: default "fisd.fisd_mergedissue"

    WRDS credentials are deliberately not handled here. The caller should create an
    authenticated connection and pass it in.
    """

    connection = source.get("connection")
    if connection is None:
        raise ValueError("WRDS TRACE Enhanced loading requires source['connection'].")

    trace_table = source.get("trace_table", "trace.trace_enhanced")
    fisd_table = source.get("fisd_table", "fisd.fisd_mergedissue")
    start = source.get("start")
    end = source.get("end")
    universe_sql = source.get("universe_sql", "1 = 1")

    date_filter = ""
    params: dict[str, Any] = {}
    if start is not None:
        date_filter += " AND t.trd_exctn_dt >= %(start)s"
        params["start"] = start
    if end is not None:
        date_filter += " AND t.trd_exctn_dt <= %(end)s"
        params["end"] = end

    sql = f"""
        SELECT
            t.cusip_id AS cusip,
            (t.trd_exctn_dt + t.trd_exctn_tm) AS ts,
            t.rptd_pr AS price,
            t.entrd_vol_qt AS par_volume,
            t.rpt_side_cd AS side_flag,
            t.cntra_mp_id AS contra_party_type,
            f.amt_outstanding,
            f.rating,
            f.maturity,
            f.industry AS sector
        FROM {trace_table} AS t
        LEFT JOIN {fisd_table} AS f
            ON t.cusip_id = f.cusip
        WHERE {universe_sql}
        {date_filter}
    """
    frame = pd.read_sql(sql, connection, params=params)
    return _canonicalize_tape(frame)


def _load_finra_public(source: Mapping[str, Any]) -> pd.DataFrame:
    """Load public FINRA TRACE-style CSV data and normalize capped volumes.

    The public feed may include exact values below dissemination caps and strings such as
    5MM+ or 1MM+ above the cap. Those capped observations are converted to the cap value,
    so `par_volume` is a lower bound for capped blocks.
    """

    path = source.get("path") or source.get("url")
    if path is None:
        raise ValueError("FINRA public loading requires source['path'] or source['url'].")

    raw = pd.read_csv(path)
    column_map = {
        "CUSIP": "cusip",
        "cusip_id": "cusip",
        "Execution Date/Time": "ts",
        "execution_datetime": "ts",
        "date_time": "ts",
        "Price": "price",
        "price": "price",
        "Quantity": "par_volume",
        "volume": "par_volume",
        "reported_volume": "par_volume",
        "Side": "side_flag",
        "side": "side_flag",
        "Contra Party Type": "contra_party_type",
        "contra_party_type": "contra_party_type",
    }
    renamed = raw.rename(columns={key: value for key, value in column_map.items() if key in raw})
    if "par_volume" in renamed:
        renamed["par_volume"] = renamed["par_volume"].map(_parse_public_volume)
    if "contra_party_type" not in renamed:
        renamed["contra_party_type"] = "unknown"
    if "side_flag" not in renamed:
        renamed["side_flag"] = "unknown"
    return _canonicalize_tape(renamed)


def _load_synthetic(source: Mapping[str, Any]) -> pd.DataFrame:
    config = SyntheticTapeConfig(
        **{key: value for key, value in source.items() if key in SyntheticTapeConfig.__annotations__}
    )
    rng = np.random.default_rng(config.seed)
    dates = pd.bdate_range(config.start, config.end)
    if len(dates) == 0:
        return pd.DataFrame(columns=TAPE_COLUMNS)

    bonds = _synthetic_bond_reference(config, rng)
    issuer_pressure = {issuer: 0.0 for issuer in bonds["issuer"].unique()}
    last_sign = np.zeros(config.n_bonds, dtype=float)
    rows: list[dict[str, Any]] = []

    for date in dates:
        issuer_daily_flow: dict[str, float] = {issuer: 0.0 for issuer in issuer_pressure}
        market_shock = rng.normal(0.0, 0.05)

        for bond_idx, bond in bonds.iterrows():
            issuer = str(bond["issuer"])
            base_lambda = float(bond["daily_intensity"])
            excitation = 0.35 * max(last_sign[bond_idx], 0.0) + 0.25 * abs(issuer_pressure[issuer])
            trade_count = rng.poisson(base_lambda * (1.0 + excitation))
            if trade_count == 0:
                last_sign[bond_idx] *= 0.4
                continue

            times = np.sort(rng.uniform(9.5 * 60, 16.0 * 60, size=trade_count))
            ou_pressure = 0.0
            previous_sign = last_sign[bond_idx]

            for minute_of_day in times:
                side = _next_trade_side(rng, previous_sign, config.sign_persistence)
                previous_sign = side
                last_sign[bond_idx] = side

                is_interdealer = rng.random() < config.interdealer_probability
                contra = "dealer" if is_interdealer else "customer"
                par_volume = _sample_par_volume(rng, float(bond["liquidity_scale"]))
                log_volume = np.log1p(par_volume / 1_000_000.0)

                issuer_lead_lag = config.issuer_lead_lag_bps * issuer_pressure[issuer]
                impact_bps = -2.5 * side * log_volume
                planted_reversal = config.reversal_bps_per_log_volume * side * log_volume
                ou_pressure = 0.88 * ou_pressure + impact_bps + planted_reversal
                fair_value = float(bond["base_price"]) + market_shock + float(bond["curve_slope"])
                noise = rng.normal(0.0, 0.035)
                price = fair_value + (ou_pressure + issuer_lead_lag) / 100.0 + noise

                timestamp = date + pd.Timedelta(float(minute_of_day), unit="m")
                rows.append(
                    {
                        "cusip": bond["cusip"],
                        "ts": timestamp,
                        "price": price,
                        "par_volume": par_volume,
                        "side_flag": int(side),
                        "contra_party_type": contra,
                    }
                )
                issuer_daily_flow[issuer] += side * log_volume

        for issuer, daily_flow in issuer_daily_flow.items():
            issuer_pressure[issuer] = 0.72 * issuer_pressure[issuer] + 0.08 * daily_flow

    return _canonicalize_tape(pd.DataFrame(rows))


def _synthetic_bond_reference(config: SyntheticTapeConfig, rng: np.random.Generator) -> pd.DataFrame:
    issuers = [f"ISSUER{i:03d}" for i in range(max(1, config.n_bonds // 5))]
    cusips = [f"SYN{i:06d}" for i in range(config.n_bonds)]
    percentile_ratio = (config.p10_trades_per_week / 5.0) / config.median_trades_per_day
    sigma = max(0.1, np.log(1.0 / max(percentile_ratio, 0.01)) / 1.2816)
    daily_intensity = rng.lognormal(mean=np.log(config.median_trades_per_day), sigma=sigma, size=config.n_bonds)
    daily_intensity = np.clip(daily_intensity, 0.03, 12.0)
    liquidity_scale = 0.35 + 1.8 * (daily_intensity / np.median(daily_intensity))

    return pd.DataFrame(
        {
            "cusip": cusips,
            "issuer": rng.choice(issuers, size=config.n_bonds),
            "daily_intensity": daily_intensity,
            "liquidity_scale": liquidity_scale,
            "base_price": rng.normal(100.0, 3.0, size=config.n_bonds),
            "curve_slope": rng.normal(0.0, 0.25, size=config.n_bonds),
        }
    )


def _next_trade_side(rng: np.random.Generator, previous_sign: float, persistence: float) -> int:
    if previous_sign != 0 and rng.random() < persistence:
        return 1 if previous_sign > 0 else -1
    return 1 if rng.random() < 0.5 else -1


def _sample_par_volume(rng: np.random.Generator, liquidity_scale: float) -> float:
    lots = rng.lognormal(mean=np.log(450_000.0 * liquidity_scale), sigma=0.95)
    return float(np.clip(np.round(lots / 1_000.0) * 1_000.0, 25_000.0, 25_000_000.0))


def _parse_public_volume(value: Any) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    text = str(value).strip().upper().replace("$", "").replace(",", "")
    text = text.removesuffix("+")
    multiplier = 1.0
    if text.endswith("MM"):
        multiplier = 1_000_000.0
        text = text[:-2]
    elif text.endswith("M"):
        multiplier = 1_000_000.0
        text = text[:-1]
    elif text.endswith("K"):
        multiplier = 1_000.0
        text = text[:-1]
    return float(text) * multiplier


def _canonicalize_tape(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in TAPE_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Tape is missing required columns: {missing}")

    tape = frame.loc[:, TAPE_COLUMNS].copy()
    tape["cusip"] = tape["cusip"].astype(str)
    tape["ts"] = pd.to_datetime(tape["ts"], errors="raise")
    tape["price"] = pd.to_numeric(tape["price"], errors="raise")
    tape["par_volume"] = pd.to_numeric(tape["par_volume"], errors="raise")
    tape["side_flag"] = tape["side_flag"].map(_normalize_side_flag)
    tape["contra_party_type"] = tape["contra_party_type"].astype(str).str.lower()
    tape = tape.sort_values(["ts", "cusip"], kind="mergesort").reset_index(drop=True)
    return tape


def _normalize_side_flag(value: Any) -> int | str:
    if pd.isna(value):
        return "unknown"
    if isinstance(value, (int, float, np.integer, np.floating)) and value in {-1, 1}:
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "+1", "buy", "b", "customer sell", "client sell", "client sells"}:
        return 1
    if text in {"-1", "sell", "s", "customer buy", "client buy", "client buys"}:
        return -1
    return text
