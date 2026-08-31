"""Lightweight positive-control recovery checks for BondSim outputs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RecoveryResult:
    """A named recovery metric with direction and sample size."""

    name: str
    estimate: float
    expected_sign: int
    n: int
    passed: bool
    detail: str


def run_recovery_checks(
    public_trades: pd.DataFrame,
    truth: pd.DataFrame,
    horizon: str | pd.Timedelta = "1D",
) -> dict[str, object]:
    """Run observable recovery checks without adding truth to public output."""

    _require_public_columns(public_trades)
    _require_truth_columns(truth)
    horizon_td = pd.Timedelta(horizon)
    results = [
        reversal_recovery(public_trades, truth, horizon_td),
        sign_persistence_recovery(public_trades),
        leadlag_recovery(public_trades, truth, horizon_td),
    ]
    return {
        "passed": all(result.passed for result in results),
        "results": [result.__dict__ for result in results],
    }


def run_public_recovery_checks(
    public_trades: pd.DataFrame,
    horizon: str | pd.Timedelta = "1D",
) -> dict[str, object]:
    """Run positive and negative controls from public fields only."""

    _require_public_columns(public_trades)
    public = _ordered_public(public_trades)
    horizon_td = pd.Timedelta(horizon)
    results = [
        public_large_print_reversal(public, horizon_td),
        sign_persistence_recovery(public),
        public_leadlag(public, horizon_td, "leader_to_follower"),
        public_leadlag(public, horizon_td, "follower_to_leader"),
        public_cross_issuer(public, horizon_td),
    ]
    return {"passed": all(result.passed for result in results), "results": [result.__dict__ for result in results]}


def run_oracle_accounting_checks(truth: pd.DataFrame) -> dict[str, object]:
    """Check hidden-ledger accounting identities."""

    _require_truth_columns(truth)
    numeric = [
        "latent_fair_value",
        "ou_pressure",
        "permanent_impact_state",
        "ordinary_temporary_impact_state",
        "planted_large_print_state",
        "planted_leadlag_state",
        "latent_mid_without_planted_effects",
        "latent_mid_with_planted_effects",
        "transaction_concession",
        "observation_noise",
    ]
    missing = [column for column in numeric if column not in truth.columns]
    failures = []
    if missing:
        failures.append(f"missing truth numeric fields: {missing}")
    if not missing:
        finite = np.isfinite(truth[numeric].astype(float).to_numpy()).all()
        if not finite:
            failures.append("nonfinite truth component")
        diff = (
            truth["latent_mid_with_planted_effects"].astype(float)
            - truth["latent_mid_without_planted_effects"].astype(float)
            - truth["planted_large_print_state"].astype(float)
            - truth["planted_leadlag_state"].astype(float)
        ).abs()
        tolerance = float(diff.max()) if len(diff) else 0.0
        if tolerance > 1e-8:
            failures.append(f"planted-state accounting identity max error {tolerance}")
    return {"passed": not failures, "failures": failures}


def oracle_large_print_reversal_target(
    public_trades: pd.DataFrame,
    truth: pd.DataFrame,
    horizon: str | pd.Timedelta = "1D",
    *,
    reversal_amplitude: float = 0.08,
    maximum_anchors: int = 300,
) -> RecoveryResult:
    """Measure the realized large-print reversal target from hidden state.

    The public estimator is intentionally noisy because it observes transaction
    prices. The Gate 3 magnitude gate should compare that public estimate with
    the realized structural contribution for the same anchor-selection rule,
    not with the unit-size configuration default.
    """

    _require_public_columns(public_trades)
    _require_truth_columns(truth)
    public = _ordered_public(public_trades)
    threshold = public.groupby("synthetic_bond_id")["notional"].transform(lambda s: s.quantile(0.90))
    anchors = _bounded_anchors(public.loc[public["notional"] >= threshold].copy(), maximum_anchors)
    if anchors.empty:
        return RecoveryResult("oracle_reversal_target", np.nan, -1, 0, False, "no public large prints")

    truth_indexed = truth.set_index("event_id", drop=False)
    signed_contributions: list[float] = []
    horizon_td = pd.Timedelta(horizon)
    for anchor in anchors.itertuples(index=False):
        if anchor.event_id not in truth_indexed.index:
            continue
        candidates = public[
            (public["synthetic_bond_id"] == anchor.synthetic_bond_id)
            & (public["timestamp_utc"] >= anchor.timestamp_utc + horizon_td)
        ]
        if candidates.empty:
            continue
        future = candidates.iloc[0]
        if future["event_id"] not in truth_indexed.index:
            continue
        anchor_truth = truth_indexed.loc[anchor.event_id]
        future_truth = truth_indexed.loc[future["event_id"]]
        threshold_value = float(anchor_truth["large_print_threshold"])
        if not np.isfinite(threshold_value) or threshold_value <= 0.0:
            threshold_value = max(float(anchor.notional), 1.0)
        normalized_size = min(4.0, np.sqrt(float(anchor.notional) / max(threshold_value, 1.0)))
        post_anchor_state = float(anchor_truth["planted_large_print_state"]) + float(anchor.side) * reversal_amplitude * normalized_size
        contribution = float(anchor.side) * (float(future_truth["planted_large_print_state"]) - post_anchor_state)
        signed_contributions.append(contribution)

    if not signed_contributions:
        return RecoveryResult("oracle_reversal_target", np.nan, -1, 0, False, "no matched future truth rows")
    estimate = float(np.nanmean(signed_contributions))
    return RecoveryResult(
        "oracle_reversal_target",
        estimate,
        -1,
        int(np.isfinite(signed_contributions).sum()),
        bool(np.isfinite(estimate) and estimate < 0.0),
        "truth-ledger large-print state contribution for public anchor set",
    )


def public_large_print_reversal(public_trades: pd.DataFrame, horizon: pd.Timedelta) -> RecoveryResult:
    """Estimate large-print reversal using only public notional and prices."""

    public = _ordered_public(public_trades)
    threshold = public.groupby("synthetic_bond_id")["notional"].transform(lambda s: s.quantile(0.90))
    anchors = _bounded_anchors(public.loc[public["notional"] >= threshold, ["event_id"]], 300)
    if anchors.empty:
        return RecoveryResult("public_reversal", np.nan, -1, 0, False, "no public large prints")
    rows = _future_price_rows(public, anchors, horizon)
    if rows.empty:
        return RecoveryResult("public_reversal", np.nan, -1, 0, False, "no future public prices at horizon")
    signed_move = rows["side"].to_numpy(dtype=float) * (rows["future_price"].to_numpy(dtype=float) - rows["price"].to_numpy(dtype=float))
    estimate = float(np.nanmean(signed_move))
    return RecoveryResult(
        "public_reversal",
        estimate,
        -1,
        int(np.isfinite(signed_move).sum()),
        bool(np.isfinite(estimate) and estimate < 0.0),
        "public 90th percentile notional signed future price move",
    )


def public_leadlag(public_trades: pd.DataFrame, horizon: pd.Timedelta, direction: str) -> RecoveryResult:
    """Estimate same-issuer lead-lag with leaders inferred from activity."""

    public = _ordered_public(public_trades)
    counts = public.groupby("synthetic_bond_id").size().sort_values(ascending=False)
    leaders = set()
    followers = set()
    for _, group in public.groupby("synthetic_issuer_id"):
        issuer_counts = group.groupby("synthetic_bond_id").size().sort_values(ascending=False)
        if len(issuer_counts) < 2:
            continue
        leaders.add(str(issuer_counts.index[0]))
        followers.update(str(item) for item in issuer_counts.index[-min(3, len(issuer_counts) - 1):])
    if direction == "leader_to_follower":
        anchors = _bounded_anchors(public[public["synthetic_bond_id"].isin(leaders)], 150)
        target_filter = lambda frame, anchor: frame[
            (frame["synthetic_issuer_id"] == anchor.synthetic_issuer_id)
            & (frame["synthetic_bond_id"].isin(followers))
            & (frame["synthetic_bond_id"] != anchor.synthetic_bond_id)
        ]
        expected = 1
    elif direction == "follower_to_leader":
        anchors = _bounded_anchors(public[public["synthetic_bond_id"].isin(followers)], 150)
        target_filter = lambda frame, anchor: frame[
            (frame["synthetic_issuer_id"] == anchor.synthetic_issuer_id)
            & (frame["synthetic_bond_id"].isin(leaders))
        ]
        expected = 0
    else:
        raise ValueError(f"unknown leadlag direction: {direction}")
    estimate, n = _leadlag_estimate(public, anchors, target_filter, horizon)
    if direction == "leader_to_follower":
        passed = bool(np.isfinite(estimate) and estimate > 0.0)
        name = "public_leader_to_follower"
    else:
        passed = bool(np.isfinite(estimate) and abs(estimate) < 0.05)
        name = "public_follower_to_leader"
    return RecoveryResult(name, estimate, expected, n, passed, direction)


def public_cross_issuer(public_trades: pd.DataFrame, horizon: pd.Timedelta) -> RecoveryResult:
    """Estimate matched cross-issuer response. This should be near zero."""

    public = _ordered_public(public_trades)
    anchors = public.iloc[:: max(1, len(public) // 500)].copy()

    def target_filter(frame: pd.DataFrame, anchor: object) -> pd.DataFrame:
        other = frame[frame["synthetic_issuer_id"] != anchor.synthetic_issuer_id]
        if other.empty:
            return other
        issuer = sorted(other["synthetic_issuer_id"].astype(str).unique())[0]
        return other[other["synthetic_issuer_id"].astype(str).eq(issuer)]

    estimate, n = _leadlag_estimate(public, anchors, target_filter, horizon)
    return RecoveryResult(
        "public_cross_issuer",
        estimate,
        0,
        n,
        bool(np.isfinite(estimate) and abs(estimate) < 0.05),
        "matched cross-issuer signed response",
    )


def reversal_recovery(
    public_trades: pd.DataFrame,
    truth: pd.DataFrame,
    horizon: pd.Timedelta,
) -> RecoveryResult:
    """Estimate signed post-large-print move from public trade prices."""

    planted = _bounded_anchors(_truth_events(truth, "large_print_reversal"), 1000)
    if planted.empty:
        return RecoveryResult("reversal", np.nan, -1, 0, False, "no planted large-print events")
    rows = _future_price_rows(public_trades, planted[["event_id"]], horizon)
    if rows.empty:
        return RecoveryResult("reversal", np.nan, -1, 0, False, "no future public prices at horizon")
    signed_move = rows["side"].to_numpy(dtype=float) * (rows["future_price"].to_numpy(dtype=float) - rows["price"].to_numpy(dtype=float))
    estimate = float(np.nanmean(signed_move))
    return RecoveryResult(
        "reversal",
        estimate,
        -1,
        int(np.isfinite(signed_move).sum()),
        bool(np.isfinite(estimate) and estimate < 0.0),
        "customer-side signed future price move after planted large prints",
    )


def sign_persistence_recovery(public_trades: pd.DataFrame) -> RecoveryResult:
    """Estimate next-event same-side probability within each synthetic bond."""

    ordered = _ordered_public(public_trades)
    ordered["next_side"] = ordered.groupby("synthetic_bond_id")["side"].shift(-1)
    comparable = ordered.dropna(subset=["next_side"])
    if comparable.empty:
        return RecoveryResult("sign_persistence", np.nan, 1, 0, False, "no consecutive same-bond events")
    same = (comparable["side"].astype(int) == comparable["next_side"].astype(int)).astype(float)
    estimate = float(same.mean() - 0.5)
    return RecoveryResult(
        "sign_persistence",
        estimate,
        1,
        int(len(comparable)),
        bool(np.isfinite(estimate) and estimate > 0.0),
        "next same-bond event same-side probability minus 0.5",
    )


def leadlag_recovery(
    public_trades: pd.DataFrame,
    truth: pd.DataFrame,
    horizon: pd.Timedelta,
) -> RecoveryResult:
    """Estimate follower price response after planted leader events."""

    planted = _truth_events(truth, "leader_follower")
    if planted.empty:
        return RecoveryResult("leadlag", np.nan, 1, 0, False, "no planted leader events")
    public = _ordered_public(public_trades)
    leader_rows = _bounded_anchors(planted[["event_id"]].merge(public, on="event_id", how="inner"), 150)
    estimates: list[float] = []
    for leader in leader_rows.itertuples(index=False):
        issuer_events = public[
            (public["synthetic_issuer_id"] == leader.synthetic_issuer_id)
            & (public["synthetic_bond_id"] != leader.synthetic_bond_id)
            & (public["timestamp_utc"] > leader.timestamp_utc)
            & (public["timestamp_utc"] <= leader.timestamp_utc + horizon)
        ]
        if issuer_events.empty:
            continue
        for follower_id, follower_events in issuer_events.groupby("synthetic_bond_id", sort=False):
            history = public[
                (public["synthetic_bond_id"] == follower_id)
                & (public["timestamp_utc"] <= leader.timestamp_utc)
            ]
            if history.empty:
                if len(follower_events) < 2:
                    continue
                baseline = float(follower_events.iloc[0]["price"])
                response_events = follower_events.iloc[1:]
            else:
                baseline = float(history.iloc[-1]["price"])
                response_events = follower_events
            signed_response = float(leader.side) * (response_events["price"].astype(float) - baseline)
            estimates.append(float(signed_response.mean()))
    if not estimates:
        return RecoveryResult("leadlag", np.nan, 1, 0, False, "no follower observations inside horizon")
    estimate = float(np.nanmean(estimates))
    return RecoveryResult(
        "leadlag",
        estimate,
        1,
        len(estimates),
        bool(np.isfinite(estimate) and estimate > 0.0),
        "same-issuer follower signed price response after planted leader events",
    )


def _future_price_rows(public_trades: pd.DataFrame, event_ids: pd.DataFrame, horizon: pd.Timedelta) -> pd.DataFrame:
    public = _ordered_public(public_trades)
    anchors = event_ids.merge(public, on="event_id", how="inner", suffixes=("", "_anchor"))
    matches: list[dict[str, object]] = []
    for anchor in anchors.itertuples(index=False):
        candidates = public[
            (public["synthetic_bond_id"] == anchor.synthetic_bond_id)
            & (public["timestamp_utc"] >= anchor.timestamp_utc + horizon)
        ]
        if candidates.empty:
            continue
        future = candidates.iloc[0]
        matches.append(
            {
                "event_id": anchor.event_id,
                "side": anchor.side,
                "price": anchor.price,
                "future_price": future["price"],
            }
        )
    return pd.DataFrame(matches)


def _leadlag_estimate(public: pd.DataFrame, anchors: pd.DataFrame, target_filter: object, horizon: pd.Timedelta) -> tuple[float, int]:
    estimates: list[float] = []
    event_times = pd.to_datetime(public["timestamp_utc"], utc=True).astype("int64").to_numpy()
    horizon_ns = int(horizon.value)
    for anchor in anchors.itertuples(index=False):
        anchor_ns = int(pd.Timestamp(anchor.timestamp_utc).value)
        start = int(np.searchsorted(event_times, anchor_ns, side="right"))
        end = int(np.searchsorted(event_times, anchor_ns + horizon_ns, side="right"))
        candidates = public.iloc[start:end]
        targets = target_filter(candidates, anchor)
        if targets.empty:
            continue
        for target_id, target_events in targets.groupby("synthetic_bond_id", sort=False):
            history = public[
                (public["synthetic_bond_id"] == target_id)
                & (public["timestamp_utc"] <= anchor.timestamp_utc)
            ]
            if history.empty:
                if len(target_events) < 2:
                    continue
                baseline = float(target_events.iloc[0]["price"])
                response_events = target_events.iloc[1:]
            else:
                baseline = float(history.iloc[-1]["price"])
                response_events = target_events
            signed_response = float(anchor.side) * (response_events["price"].astype(float) - baseline)
            estimates.append(float(signed_response.mean()))
    if not estimates:
        return np.nan, 0
    return float(np.nanmean(estimates)), len(estimates)


def _truth_events(truth: pd.DataFrame, effect_id: str) -> pd.DataFrame:
    planted = truth["planted_effect_ids"].fillna("").astype(str).str.contains(effect_id, regex=False)
    return truth.loc[planted].copy()


def _ordered_public(public_trades: pd.DataFrame) -> pd.DataFrame:
    result = public_trades.copy()
    result["timestamp_utc"] = pd.to_datetime(result["timestamp_utc"], utc=True)
    return result.sort_values(["timestamp_utc", "event_id"]).reset_index(drop=True)


def _bounded_anchors(frame: pd.DataFrame, maximum: int) -> pd.DataFrame:
    if len(frame) <= maximum:
        return frame
    step = max(1, len(frame) // maximum)
    return frame.iloc[::step].head(maximum).copy()


def _require_public_columns(public_trades: pd.DataFrame) -> None:
    required = {"event_id", "timestamp_utc", "synthetic_bond_id", "synthetic_issuer_id", "side", "price"}
    missing = sorted(required.difference(public_trades.columns))
    if missing:
        raise KeyError(f"public trades missing columns: {missing}")
    forbidden = {"latent_fair_value", "planted_large_print_state", "planted_leadlag_state", "source_bond_id", "source_issuer_id"}
    leaked = sorted(forbidden.intersection(public_trades.columns))
    if leaked:
        raise ValueError(f"public trades contain truth/source columns: {leaked}")


def _require_truth_columns(truth: pd.DataFrame) -> None:
    required = {"event_id", "planted_effect_ids"}
    missing = sorted(required.difference(truth.columns))
    if missing:
        raise KeyError(f"truth ledger missing columns: {missing}")
