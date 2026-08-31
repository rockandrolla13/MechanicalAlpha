"""Truth ledger docs and parameter records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bondsim import __version__
from bondsim.hawkes.graph import HawkesGraph
from bondsim.io import write_json
from bondsim.marks.synthcity_adapter import MarkModelSelection


def write_truth_parameters(
    root: Path,
    scenario: str,
    graph: HawkesGraph,
    mark_selection: MarkModelSelection,
    liquidity_summary: dict[str, float],
    config_hash: str,
) -> dict[str, Any]:
    payload = {
        "simulator_version": __version__,
        "scenario": scenario,
        "side_semantics": "BUY=+1, SELL=-1 using TRACE rpt_side_cd mapping",
        "price_units": "par-price points; 100 means par and 0.01 means one cent",
        "notional_units": "TRACE entrd_vol_qt treated as par quantity",
        "synthcity": mark_selection.__dict__,
        "hawkes": graph.__dict__,
        "liquidity_summary": liquidity_summary,
        "config_hash": config_hash,
        "controlled_effects": {
            "large_print_reversal": "state jump side * A * sqrt(q/q90), A=0.08, half-life=0.5 trading day",
            "sign_persistence": "own same-side branching mass exceeds opposite-side mass in controlled scenarios",
            "leader_follower": "issuer leader events add side * 0.05 price points to illiquid follower leadlag state",
        },
        "nulls": {
            "controlled_null": "removes incremental large-print reversal, symmetrizes own excitation, and disables leader-follower price response"
        },
    }
    scenario_root = root / f"scenario={scenario}"
    write_json(payload, scenario_root / "parameter_truth.json")
    write_json(payload, scenario_root / "realized_truth.json")
    return payload


def write_truth_markdown(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    hawkes = payload["hawkes"]
    text = f"""# Synthetic Truth

Simulator version: `{payload['simulator_version']}`

Scenario: `{payload['scenario']}`

Config hash: `{payload['config_hash']}`

## Data And Units

- Side semantics: {payload['side_semantics']}
- Price units: {payload['price_units']}
- Notional units: {payload['notional_units']}
- Public data and truth data are physically separate.

## SynthCity And Marks

- Selected mark model: `{payload['synthcity']['selected']}`
- SynthCity version: `{payload['synthcity']['synthcity_version']}`
- Available plugins: `{payload['synthcity']['available_plugins']}`
- Failure recorded: `{payload['synthcity']['failure']}`

## Liquidity

- Realized median events per bond-session: `{payload['liquidity_summary']['median']:.6f}`
- Realized p10 events per bond-session: `{payload['liquidity_summary']['p10']:.6f}`
- Realized max events per bond-session: `{payload['liquidity_summary']['max']:.6f}`

## Hawkes Clock

- Same-side mass: `{hawkes['same_side_mass']}`
- Opposite-side mass: `{hawkes['opposite_side_mass']}`
- Leader-follower mass: `{hawkes['leader_follower_mass']}`
- Half-lives in minutes: `{hawkes['half_lives_minutes']}`
- Spectral radius: `{hawkes['spectral_radius']}`

## Controlled Effects

- Large-print reversal: {payload['controlled_effects']['large_print_reversal']}
- Sign persistence: {payload['controlled_effects']['sign_persistence']}
- Leader-follower lead-lag: {payload['controlled_effects']['leader_follower']}

## Null Definition

{payload['nulls']['controlled_null']}

## Known Limitations

- Rating, maturity, sector, duration, OAS, bid, ask, and vendor fair value were not available in local TRACE.
- Fair value uses a transaction-price proxy route in this vertical slice.
- The empirical fallback is selected because the installed SynthCity registry fails in this environment.
- No differential-privacy claim is made.
"""
    path.write_text(text)
    return path


def write_combined_truth_markdown(path: Path, payloads: list[dict[str, Any]]) -> Path:
    """Write a generated truth document covering all smoke scenarios."""

    if not payloads:
        raise ValueError("at least one truth payload is required")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Synthetic Truth",
        "",
        "This file is generated from machine-readable truth parameters.",
        "Public synthetic trades and truth ledgers are physically separate.",
        "",
        f"Simulator version: `{payloads[0]['simulator_version']}`",
        f"Config hash: `{payloads[0]['config_hash']}`",
        "",
        "## Data And Units",
        "",
        f"- Side semantics: {payloads[0]['side_semantics']}",
        f"- Price units: {payloads[0]['price_units']}",
        f"- Notional units: {payloads[0]['notional_units']}",
        "- No source identifiers are included in public output.",
        "- No differential-privacy claim is made.",
        "",
        "## Scenario Parameters",
        "",
    ]
    for payload in payloads:
        hawkes = payload["hawkes"]
        liquidity = payload["liquidity_summary"]
        lines.extend(
            [
                f"### `{payload['scenario']}`",
                "",
                f"- Selected mark model: `{payload['synthcity']['selected']}`",
                f"- SynthCity version: `{payload['synthcity']['synthcity_version']}`",
                f"- Available SynthCity plugins: `{payload['synthcity']['available_plugins']}`",
                f"- SynthCity failure notes: `{payload['synthcity']['failure']}`",
                f"- Realized median events per bond-session: `{liquidity['median']:.6f}`",
                f"- Realized p10 events per bond-session: `{liquidity['p10']:.6f}`",
                f"- Realized max events per bond-session: `{liquidity['max']:.6f}`",
                f"- Same-side Hawkes mass: `{hawkes['same_side_mass']}`",
                f"- Opposite-side Hawkes mass: `{hawkes['opposite_side_mass']}`",
                f"- Leader-follower Hawkes mass: `{hawkes['leader_follower_mass']}`",
                f"- Hawkes half-lives in minutes: `{hawkes['half_lives_minutes']}`",
                f"- Hawkes spectral radius: `{hawkes['spectral_radius']}`",
                "",
            ]
        )
    first = payloads[0]
    lines.extend(
        [
            "## Controlled Effects",
            "",
            f"- Large-print reversal: {first['controlled_effects']['large_print_reversal']}",
            f"- Sign persistence: {first['controlled_effects']['sign_persistence']}",
            f"- Leader-follower lead-lag: {first['controlled_effects']['leader_follower']}",
            "",
            "## Null Definition",
            "",
            first["nulls"]["controlled_null"],
            "",
            "## Known Limitations",
            "",
            "- Rating, maturity, sector, duration, OAS, bid, ask, and vendor fair value were not available in local TRACE.",
            "- Fair value uses a transaction-price proxy route in this smoke implementation.",
            "- SynthCity is attempted only through installed plugins; empirical fallback remains the supported baseline.",
            "- Smoke recovery checks are directional diagnostics, not full multi-seed acceptance tests.",
        ]
    )
    path.write_text("\n".join(lines) + "\n")
    return path
