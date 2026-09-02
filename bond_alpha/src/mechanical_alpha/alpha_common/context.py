"""Point-in-time context preparation for standalone alpha files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from mechanical_alpha.contracts import AlphaInputBundle

DEFAULT_EVENT_WINDOWS = (5, 10, 25)
DEFAULT_CALENDAR_WINDOWS = ("30m", "2h")
DEFAULT_EWMA_HALFLIVES = ("1d", "5d", "20d")
EPSILON = 1.0e-12


@dataclass(frozen=True)
class AlphaContext:
    """Canonical, normalized inputs used by standalone alpha files."""

    prediction_grid: pd.DataFrame
    rfqs: pd.DataFrame
    traces: pd.DataFrame
    quotes: pd.DataFrame
    bonds: pd.DataFrame


def build_context(bundle: AlphaInputBundle) -> AlphaContext:
    """Normalize public inputs once before alpha computation."""

    return AlphaContext(
        prediction_grid=prediction_grid(bundle),
        rfqs=normalise_rfqs(bundle.rfqs),
        traces=normalise_trace_events(bundle.events),
        quotes=normalise_quotes(bundle.quotes),
        bonds=normalise_bonds(bundle.bonds),
    )


def compute_from_context(
    context: AlphaContext,
    add_alpha_row: object,
    *,
    event_windows: Iterable[int] = DEFAULT_EVENT_WINDOWS,
    calendar_windows: Iterable[str] = DEFAULT_CALENDAR_WINDOWS,
    ewma_halflives: Iterable[str] = DEFAULT_EWMA_HALFLIVES,
    epsilon: float = EPSILON,
) -> pd.DataFrame:
    """Build one alpha frame from a row-level alpha function."""

    if context.prediction_grid.empty:
        return context.prediction_grid.copy()
    rows: list[dict[str, object]] = []
    for prediction in context.prediction_grid.itertuples(index=False):
        asof = pd.Timestamp(prediction.prediction_timestamp)
        row: dict[str, object] = {
            "prediction_timestamp": asof,
            "bond_id": prediction.bond_id,
            "issuer_id": prediction.issuer_id,
        }
        add_alpha_row(row, context, prediction.bond_id, asof, event_windows, calendar_windows, ewma_halflives, epsilon)
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["bond_id", "prediction_timestamp"]).reset_index(drop=True)


def prediction_grid(bundle: AlphaInputBundle) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if bundle.rfqs is not None and not bundle.rfqs.empty:
        frames.append(
            pd.DataFrame(
                {
                    "prediction_timestamp": pd.to_datetime(bundle.rfqs["timestamp"], utc=False),
                    "bond_id": bundle.rfqs["bond_id"].astype(str),
                    "issuer_id": bundle.rfqs.get("issuer_id", pd.Series([pd.NA] * len(bundle.rfqs))).astype("string"),
                }
            )
        )
    if not bundle.events.empty:
        frames.append(
            pd.DataFrame(
                {
                    "prediction_timestamp": pd.to_datetime(bundle.events["prediction_timestamp"], utc=False),
                    "bond_id": bundle.events["bond_id"].astype(str),
                    "issuer_id": bundle.events["issuer_id"].astype("string"),
                }
            )
        )
    if not frames:
        return pd.DataFrame(columns=["prediction_timestamp", "bond_id", "issuer_id"])
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates()
        .sort_values(["bond_id", "prediction_timestamp"])
        .reset_index(drop=True)
    )


def normalise_rfqs(rfqs: pd.DataFrame | None) -> pd.DataFrame:
    if rfqs is None or rfqs.empty:
        return pd.DataFrame(columns=["timestamp", "bond_id", "side", "notional", "event_kind"])
    frame = rfqs.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    frame["bond_id"] = frame["bond_id"].astype(str)
    frame["side"] = pd.to_numeric(frame["side"], errors="coerce")
    frame["notional"] = pd.to_numeric(frame.get("size", frame.get("notional", np.nan)), errors="coerce")
    for column in ("dv01", "cr01", "effective_duration", "duration"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "event_kind" not in frame.columns:
        stage = frame.get("stage", frame.get("rfq_stage", "inquiry"))
        frame["event_kind"] = pd.Series(stage, index=frame.index).fillna("inquiry").astype(str).str.lower()
    return frame.sort_values(["bond_id", "timestamp"]).reset_index(drop=True)


def normalise_trace_events(events: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    frame["timestamp"] = pd.to_datetime(frame["prediction_timestamp"], utc=False)
    frame["bond_id"] = frame["bond_id"].astype(str)
    frame["side"] = pd.to_numeric(frame["side"], errors="coerce")
    frame["notional"] = pd.to_numeric(frame["notional"], errors="coerce")
    for column in ("dv01", "cr01", "effective_duration", "duration"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame.sort_values(["bond_id", "timestamp"]).reset_index(drop=True)


def normalise_quotes(quotes: pd.DataFrame | None) -> pd.DataFrame:
    if quotes is None or quotes.empty:
        return pd.DataFrame(columns=["timestamp", "bond_id", "bid", "ask", "mid", "spread"])
    frame = quotes.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=False)
    frame["bond_id"] = frame["bond_id"].astype(str)
    for column in ("bid", "ask", "mid", "spread", "source_disagreement", "composite_source_disagreement"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "spread" not in frame.columns and {"bid", "ask"}.issubset(frame.columns):
        frame["spread"] = frame["ask"] - frame["bid"]
    if "mid" not in frame.columns and {"bid", "ask"}.issubset(frame.columns):
        frame["mid"] = (frame["bid"] + frame["ask"]) / 2.0
    return frame.sort_values(["bond_id", "timestamp"]).reset_index(drop=True)


def normalise_bonds(bonds: pd.DataFrame) -> pd.DataFrame:
    frame = bonds.copy()
    frame["bond_id"] = frame["bond_id"].astype(str)
    return frame.set_index("bond_id", drop=False)


def prior(frame: pd.DataFrame, bond_id: str, asof: pd.Timestamp) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame[(frame["bond_id"] == str(bond_id)) & (frame["timestamp"] < asof)].copy()


def within_timedelta(frame: pd.DataFrame, asof: pd.Timestamp, delta: pd.Timedelta) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame[frame["timestamp"] >= asof - delta].copy()


def last_n(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    return frame.tail(int(n)).copy()


def filter_event_kind(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.DataFrame:
    if frame.empty or "event_kind" not in frame.columns:
        return frame.iloc[0:0].copy()
    wanted = {name.lower() for name in names}
    return frame[frame["event_kind"].astype(str).str.lower().isin(wanted)].copy()


def filter_firm_inquiries(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    event_match = filter_event_kind(frame, ("firm_inquiry", "firm inquiry", "firm"))
    if "request_type" not in frame.columns:
        return event_match
    request_type = frame["request_type"].fillna("").astype(str).str.lower()
    request_match = frame[request_type.isin({"firm", "firm_inquiry", "firm inquiry"})].copy()
    return pd.concat([event_match, request_match], ignore_index=False).drop_duplicates()


def transform_notional(values: pd.Series, variant: str) -> np.ndarray:
    clean = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    if variant == "raw":
        return clean
    if variant == "log":
        return np.log1p(np.maximum(clean, 0.0))
    if variant == "sqrt":
        return np.sqrt(np.maximum(clean, 0.0))
    if variant == "capped":
        finite = clean[np.isfinite(clean)]
        if finite.size == 0:
            return clean
        cap = float(np.nanquantile(finite, 0.95))
        return np.minimum(clean, cap)
    raise ValueError(f"unknown notional variant: {variant}")


def key(*parts: object) -> str:
    return "_".join(str(part).replace("-", "_").replace(" ", "_").replace(":", "").lower() for part in parts)


def interaction(left: object, right: object) -> float:
    if pd.isna(left) or pd.isna(right):
        return np.nan
    return float(left) * float(right)


def nan_if_no_obs(left: float, right: float, value: float) -> float:
    if pd.isna(left) and pd.isna(right):
        return np.nan
    return float(value)


def signed_notional_imbalance(frame: pd.DataFrame, epsilon: float) -> float:
    valid = frame[frame["side"].isin([-1, 1])].copy()
    if valid.empty:
        return np.nan
    transformed = pd.to_numeric(valid["notional"], errors="coerce").to_numpy(dtype=float)
    denominator = float(np.nansum(np.abs(transformed)))
    if denominator <= 0:
        return np.nan
    return float(np.nansum(valid["side"].to_numpy(dtype=float) * transformed) / (denominator + epsilon))


def latest_before(frame: pd.DataFrame, bond_id: str, asof: pd.Timestamp) -> pd.Series | None:
    prior_rows = prior(frame, bond_id, asof)
    if prior_rows.empty:
        return None
    return prior_rows.iloc[-1]


def quote_value(row: pd.Series | None, column: str) -> float:
    if row is None or column not in row:
        return np.nan
    value = row[column]
    return np.nan if pd.isna(value) else float(value)


def first_existing_value(row: pd.Series | None, columns: tuple[str, ...]) -> object:
    if row is None:
        return np.nan
    for column in columns:
        if column in row and pd.notna(row[column]):
            return row[column]
    return np.nan


def last_value_percentile(values: pd.Series, latest_value: object) -> float:
    if pd.isna(latest_value):
        return np.nan
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return np.nan
    return float((clean <= float(latest_value)).mean())
