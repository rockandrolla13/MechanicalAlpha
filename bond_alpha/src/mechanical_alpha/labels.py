"""Point-in-time label factory for corporate-bond alpha research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from mechanical_alpha.calendar import DEFAULT_HORIZONS, BusinessCalendar
from mechanical_alpha.events import CUSTOMER_BUY, CUSTOMER_SELL, dealer_inventory_change


@dataclass(frozen=True)
class MeaningfulMoveThreshold:
    absolute_price_cents: float | None = None
    spread_fraction: float | None = None
    volatility_units: float | None = None

    def price_points(self, row: pd.Series | None = None) -> float:
        hurdles: list[float] = []
        if self.absolute_price_cents is not None:
            hurdles.append(float(self.absolute_price_cents) / 100.0)
        if row is not None and self.spread_fraction is not None and pd.notna(row.get("spread")):
            hurdles.append(float(self.spread_fraction) * float(row["spread"]))
        if row is not None and self.volatility_units is not None and pd.notna(row.get("volatility")):
            hurdles.append(float(self.volatility_units) * float(row["volatility"]))
        return max(hurdles) if hurdles else 0.0


@dataclass(frozen=True)
class LabelConfig:
    horizons: tuple[str, ...] = DEFAULT_HORIZONS
    max_future_fair_value_staleness: pd.Timedelta = pd.Timedelta("2D")
    meaningful_move: dict[str, MeaningfulMoveThreshold] = field(default_factory=dict)
    aggressive_hurdle: dict[str, float] = field(default_factory=dict)
    toxicity_cost_hurdle: dict[str, float] = field(default_factory=dict)

    def threshold_for(self, horizon: str) -> MeaningfulMoveThreshold:
        return self.meaningful_move.get(horizon, MeaningfulMoveThreshold(absolute_price_cents=5.0))

    def aggressive_hurdle_for(self, horizon: str) -> float:
        return float(self.aggressive_hurdle.get(horizon, 0.0))

    def toxicity_hurdle_for(self, horizon: str) -> float:
        return float(self.toxicity_cost_hurdle.get(horizon, 0.0))


def make_prediction_events(events: pd.DataFrame) -> pd.DataFrame:
    """Return canonical prediction rows from RFQ or trade events."""

    frame = events.copy()
    if "prediction_timestamp" not in frame.columns:
        frame["prediction_timestamp"] = _first_existing(frame, ["feature_calculation_time", "publication_time", "receive_time", "source_event_time"])
    required = {"event_id", "bond_id", "prediction_timestamp"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"events missing required label columns: {missing}")
    frame["prediction_timestamp"] = pd.to_datetime(frame["prediction_timestamp"])
    return frame.sort_values(["bond_id", "prediction_timestamp", "event_id"]).reset_index(drop=True)


def build_label_frame(
    *,
    prediction_events: pd.DataFrame,
    fair_values: pd.DataFrame,
    event_stream: pd.DataFrame | None = None,
    calendar: BusinessCalendar | None = None,
    config: LabelConfig | None = None,
) -> pd.DataFrame:
    """Build clean-value, next-event, aggressive, markout, and RFQ decision labels."""

    cal = calendar or BusinessCalendar.from_dates()
    cfg = config or LabelConfig()
    base = make_prediction_events(prediction_events)
    fv = _prepare_fair_values(fair_values)
    stream = make_prediction_events(event_stream if event_stream is not None else prediction_events)

    labels = base[["event_id", "bond_id", "prediction_timestamp"]].copy()
    if "issuer_id" in base:
        labels["issuer_id"] = base["issuer_id"]

    for horizon in cfg.horizons:
        labels[f"horizon_end_{horizon}"] = labels["prediction_timestamp"].map(lambda ts: cal.add_horizon(ts, horizon))
        current_rows = _asof_values(base, fv, "prediction_timestamp", "prediction_timestamp")
        future_cutoffs = labels[["event_id", f"horizon_end_{horizon}"]].rename(columns={f"horizon_end_{horizon}": "future_cutoff"})
        future_base = base.merge(future_cutoffs, on="event_id", how="left")
        future_rows = _asof_values(future_base, fv, "future_cutoff", "future_cutoff")

        current_value = current_rows["fair_value"]
        future_value = future_rows["fair_value"]
        age = labels[f"horizon_end_{horizon}"] - future_rows["effective_time"]
        stale = age > cfg.max_future_fair_value_staleness
        missing = current_value.isna() | future_value.isna() | stale

        labels[f"price_target_{horizon}"] = np.where(missing, np.nan, future_value - current_value)
        labels[f"label_censored_{horizon}"] = missing
        if {"oas", "duration"}.issubset(fv.columns):
            delta_oas = future_rows["oas"] - current_rows["oas"]
            valid_oas = ~missing & current_rows["oas"].notna() & future_rows["oas"].notna() & current_rows["duration"].notna()
            labels[f"oas_price_equivalent_{horizon}"] = np.where(valid_oas, -current_rows["duration"] * delta_oas, np.nan)

        labels[f"signed_move_{horizon}"] = _signed_move(base, labels[f"price_target_{horizon}"])
        hurdle = cfg.aggressive_hurdle_for(horizon)
        labels[f"aggressive_{horizon}"] = np.where(
            labels[f"signed_move_{horizon}"].isna(), np.nan, (labels[f"signed_move_{horizon}"] > hurdle).astype(int)
        )
        labels[f"dealer_markout_{horizon}"] = _dealer_markout(base, future_value)
        cost = cfg.toxicity_hurdle_for(horizon)
        labels[f"dealer_toxic_{horizon}"] = np.where(
            labels[f"dealer_markout_{horizon}"].isna(), np.nan, (labels[f"dealer_markout_{horizon}"] < -cost).astype(int)
        )

    labels = labels.merge(_next_event_labels(base, stream, "rfq", lambda x: x.get("source") == "rfq"), on="event_id", how="left")
    labels = labels.merge(
        _next_event_labels(base, stream, "executed_rfq", lambda x: x.get("source") == "rfq" and bool(x.get("executed", False))),
        on="event_id",
        how="left",
    )
    labels = labels.merge(
        _next_event_labels(base, stream, "trace", lambda x: x.get("source") == "trace" and bool(x.get("side_valid", False))),
        on="event_id",
        how="left",
    )
    labels = labels.merge(_first_meaningful_move_labels(base, fv, cfg), on="event_id", how="left")
    labels = labels.merge(_rfq_decision_labels(base), on="event_id", how="left")
    return labels


def label_coverage_report(labels: pd.DataFrame, attributes: pd.DataFrame, horizons: Iterable[str] = DEFAULT_HORIZONS) -> pd.DataFrame:
    """Summarize label coverage by bond, issuer, rating, liquidity bucket, and horizon."""

    merged = labels.merge(attributes, on="bond_id", how="left", suffixes=("", "_attr"))
    group_fields = [field for field in ("bond_id", "issuer_id", "rating", "liquidity_bucket") if field in merged.columns]
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        column = f"price_target_{horizon}"
        if column not in merged:
            continue
        grouped = merged.groupby(group_fields, dropna=False)[column]
        for keys, series in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)
            row = dict(zip(group_fields, keys, strict=False))
            row.update(
                {
                    "horizon": horizon,
                    "rows": int(len(series)),
                    "labeled_rows": int(series.notna().sum()),
                    "coverage": float(series.notna().mean()) if len(series) else 0.0,
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _prepare_fair_values(fair_values: pd.DataFrame) -> pd.DataFrame:
    fv = fair_values.copy()
    rename_map = {
        "timestamp": "effective_time",
        "publication_timestamp": "publication_time",
        "revision_timestamp": "revision_time",
    }
    fv = fv.rename(columns={k: v for k, v in rename_map.items() if k in fv.columns and v not in fv.columns})
    if "effective_time" not in fv.columns:
        raise ValueError("fair_values must include effective_time or timestamp")
    if "publication_time" not in fv.columns:
        fv["publication_time"] = fv["effective_time"]
    if "revision_time" not in fv.columns:
        fv["revision_time"] = fv["publication_time"]
    for column in ("effective_time", "publication_time", "revision_time"):
        fv[column] = pd.to_datetime(fv[column])
    required = {"bond_id", "effective_time", "publication_time", "fair_value"}
    missing = sorted(required.difference(fv.columns))
    if missing:
        raise ValueError(f"fair_values missing required columns: {missing}")
    return fv.sort_values(["bond_id", "effective_time", "publication_time", "revision_time"]).reset_index(drop=True)


def _asof_values(events: pd.DataFrame, fair_values: pd.DataFrame, event_time_col: str, cutoff_col: str) -> pd.DataFrame:
    rows = []
    grouped = {bond_id: group for bond_id, group in fair_values.groupby("bond_id", sort=False)}
    for _, event in events.iterrows():
        cutoff = pd.Timestamp(event[cutoff_col])
        effective_cutoff = pd.Timestamp(event[event_time_col])
        candidates = grouped.get(event["bond_id"])
        if candidates is None:
            rows.append({})
            continue
        usable = candidates[
            (candidates["effective_time"] <= effective_cutoff)
            & (candidates["publication_time"] <= cutoff)
            & (candidates["revision_time"] <= cutoff)
        ]
        rows.append({} if usable.empty else usable.iloc[-1].to_dict())
    out = pd.DataFrame(rows)
    for column in ("fair_value", "effective_time", "oas", "duration"):
        if column not in out:
            out[column] = np.nan
    return out


def _next_event_labels(base: pd.DataFrame, stream: pd.DataFrame, prefix: str, selector) -> pd.DataFrame:
    chosen = stream[stream.apply(selector, axis=1)].sort_values(["bond_id", "prediction_timestamp", "event_id"])
    by_bond = {bond_id: group for bond_id, group in chosen.groupby("bond_id", sort=False)}
    rows = []
    for _, row in base.iterrows():
        group = by_bond.get(row["bond_id"])
        result = {"event_id": row["event_id"], f"next_{prefix}_side": np.nan, f"time_to_next_{prefix}_seconds": np.nan}
        if group is not None:
            future = group[group["prediction_timestamp"] > row["prediction_timestamp"]]
            if not future.empty:
                next_row = future.iloc[0]
                result[f"next_{prefix}_side"] = next_row.get("customer_side", np.nan)
                delta = pd.Timestamp(next_row["prediction_timestamp"]) - pd.Timestamp(row["prediction_timestamp"])
                result[f"time_to_next_{prefix}_seconds"] = float(delta.total_seconds())
        rows.append(result)
    return pd.DataFrame(rows)


def _rfq_decision_labels(events: pd.DataFrame) -> pd.DataFrame:
    columns = ["responded", "firmed_up", "won", "executed", "response_latency_ms", "quoted_spread", "quoted_price", "realized_edge"]
    rows = []
    for _, row in events.iterrows():
        result = {"event_id": row["event_id"]}
        for column in columns:
            result[column] = row.get(column, np.nan)
        rows.append(result)
    return pd.DataFrame(rows)


def _first_meaningful_move_labels(events: pd.DataFrame, fair_values: pd.DataFrame, config: LabelConfig) -> pd.DataFrame:
    grouped = {bond_id: group.sort_values("effective_time") for bond_id, group in fair_values.groupby("bond_id", sort=False)}
    rows = []
    for _, event in events.iterrows():
        event_time = pd.Timestamp(event["prediction_timestamp"])
        current = _asof_values(pd.DataFrame([event]), fair_values, "prediction_timestamp", "prediction_timestamp")
        result = {
            "event_id": event["event_id"],
            "time_to_next_meaningful_fv_move_seconds": np.nan,
            "direction_first_meaningful_fv_move": np.nan,
        }
        if current["fair_value"].isna().iloc[0]:
            rows.append(result)
            continue
        threshold = config.threshold_for("30m").price_points(event)
        candidates = grouped.get(event["bond_id"])
        if candidates is None:
            rows.append(result)
            continue
        usable = candidates[
            (candidates["effective_time"] > event_time)
            & (candidates["publication_time"] <= candidates["effective_time"])
            & (candidates["revision_time"] <= candidates["effective_time"])
        ].copy()
        if usable.empty:
            rows.append(result)
            continue
        usable["move"] = usable["fair_value"] - float(current["fair_value"].iloc[0])
        meaningful = usable[usable["move"].abs() > threshold]
        if not meaningful.empty:
            first = meaningful.iloc[0]
            result["time_to_next_meaningful_fv_move_seconds"] = float(
                (pd.Timestamp(first["effective_time"]) - event_time).total_seconds()
            )
            result["direction_first_meaningful_fv_move"] = int(np.sign(first["move"]))
        rows.append(result)
    return pd.DataFrame(rows)


def _signed_move(events: pd.DataFrame, price_target: pd.Series) -> pd.Series:
    if "customer_side" not in events:
        return pd.Series(np.nan, index=events.index)
    side = events["customer_side"].where(events["customer_side"].isin([CUSTOMER_BUY, CUSTOMER_SELL]))
    return side * price_target


def _dealer_markout(events: pd.DataFrame, future_fair_value: pd.Series) -> pd.Series:
    required = {"customer_side", "executed_notional", "execution_price"}
    if not required.issubset(events.columns):
        return pd.Series(np.nan, index=events.index)
    values = []
    for idx, row in events.iterrows():
        if pd.isna(future_fair_value.loc[idx]) or pd.isna(row["customer_side"]) or pd.isna(row["execution_price"]):
            values.append(np.nan)
            continue
        signed_inventory = np.sign(dealer_inventory_change(int(row["customer_side"]), float(row.get("executed_notional", 0.0))))
        values.append(signed_inventory * (float(future_fair_value.loc[idx]) - float(row["execution_price"])))
    return pd.Series(values, index=events.index)


def _first_existing(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    for column in columns:
        if column in frame:
            return frame[column]
    raise ValueError(f"none of these timestamp columns exist: {columns}")
