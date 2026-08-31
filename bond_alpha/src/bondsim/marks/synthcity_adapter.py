"""SynthCity adapter with empirical fallback."""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarkModelSelection:
    selected: str
    synthcity_version: str
    available_plugins: list[str]
    candidates: list[dict[str, object]]
    failure: str | None


def run_mark_tournament(events: pd.DataFrame, candidate_names: list[str], report_root: Path, model_root: Path) -> MarkModelSelection:
    """Run a small mark-model tournament and select only valid reloaded models.

    The empirical conditional bootstrap is always evaluated. SynthCity plugins
    must import, fit, reload, generate valid rows, and beat the fallback's simple
    fidelity score before they can win.
    """

    version, plugins, registry_failure = _plugin_registry()
    candidates: list[dict[str, object]] = []
    fallback_score = _fallback_score(events)
    candidates.append(
        {
            "candidate": "empirical_fallback",
            "available": True,
            "fit_success": True,
            "serialization_reload_success": True,
            "validity_success": True,
            "fidelity_score": fallback_score,
            "selected": True,
            "notes": "Hierarchical empirical conditional bootstrap baseline.",
        }
    )
    selected = "empirical_fallback"
    failure_notes: list[str] = []
    if registry_failure:
        failure_notes.append(registry_failure)
    available = set(plugins)
    for name in candidate_names:
        row = _try_synthcity_candidate(name, available, events, model_root)
        candidates.append(row)
        if row.get("notes"):
            failure_notes.append(f"{name}: {row['notes']}")
        if (
            row["available"]
            and row["fit_success"]
            and row["serialization_reload_success"]
            and row["validity_success"]
            and float(row["fidelity_score"]) <= fallback_score
        ):
            candidates[0]["selected"] = False
            row["selected"] = True
            selected = name
            break
    selection = MarkModelSelection(
        selected=selected,
        synthcity_version=version,
        available_plugins=list(plugins),
        candidates=candidates,
        failure="; ".join(failure_notes) if failure_notes else None,
    )
    write_tournament_report(selection, report_root, model_root)
    return selection


def inspect_synthcity() -> MarkModelSelection:
    try:
        import synthcity

        version = getattr(synthcity, "__version__", "unknown")
        from synthcity.plugins import Plugins

        plugins = Plugins().list()
        return MarkModelSelection("empirical_fallback", str(version), list(plugins), [], None)
    except Exception as exc:
        return MarkModelSelection("empirical_fallback", "importable_but_registry_failed", [], [], f"{type(exc).__name__}: {exc}")


def write_tournament_report(selection: MarkModelSelection, report_root: Path, model_root: Path) -> None:
    report_root.mkdir(parents=True, exist_ok=True)
    model_root.mkdir(parents=True, exist_ok=True)
    rows = selection.candidates or [
        {
            "candidate": selection.selected,
            "available": True,
            "fit_success": True,
            "serialization_reload_success": True,
            "validity_success": True,
            "fidelity_score": 0.0,
            "selected": True,
            "notes": selection.failure or "Empirical fallback selected as robust baseline.",
        }
    ]
    pd.DataFrame(rows).to_csv(report_root / "mark_model_tournament.csv", index=False)
    selected_row = next((row for row in rows if row.get("selected")), rows[0])
    (report_root / "mark_model_tournament.md").write_text(
        f"""# Mark Model Tournament

Selected model: `{selection.selected}`.

SynthCity version: `{selection.synthcity_version}`.

Available plugins: `{selection.available_plugins}`.

Failure: `{selection.failure}`.

Selected candidate details:

```text
{selected_row}
```

All SynthCity candidates must pass availability, fit, pickle reload, schema validity, and a simple mark-fidelity check.
The empirical conditional bootstrap is selected unless a SynthCity model is at least as valid and useful as the fallback.
SynthCity remains behind an adapter and does not control timestamps, identifiers, prices, or truth labels.
"""
    )
    (model_root / "selected_model.json").write_text(
        json.dumps(
            {
                "selected": selection.selected,
                "synthcity_version": selection.synthcity_version,
                "available_plugins": selection.available_plugins,
                "reason": selected_row.get("notes", "selected by tournament"),
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n"
    )


def _plugin_registry() -> tuple[str, list[str], str | None]:
    try:
        import synthcity
        from synthcity.plugins import Plugins

        version = str(getattr(synthcity, "__version__", "unknown"))
        return version, list(Plugins().list()), None
    except Exception as exc:
        return "importable_but_registry_failed", [], f"registry failed: {type(exc).__name__}: {exc}"


def _try_synthcity_candidate(name: str, available: set[str], events: pd.DataFrame, model_root: Path) -> dict[str, object]:
    row: dict[str, object] = {
        "candidate": name,
        "available": name in available,
        "fit_success": False,
        "serialization_reload_success": False,
        "validity_success": False,
        "fidelity_score": float("inf"),
        "selected": False,
        "notes": "",
    }
    if name not in available:
        row["notes"] = "plugin not available in installed SynthCity registry"
        return row
    try:
        from synthcity.plugins import Plugins
        from synthcity.plugins.core.dataloader import GenericDataLoader

        train = _mark_frame(events).head(2500)
        plugin = Plugins().get(name)
        plugin.fit(GenericDataLoader(train))
        row["fit_success"] = True
        candidate_dir = model_root / name / "0"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        path = candidate_dir / "model.pkl"
        path.write_bytes(pickle.dumps(plugin))
        reloaded = pickle.loads(path.read_bytes())
        generated = reloaded.generate(count=min(500, max(10, len(train) // 5))).dataframe()
        row["serialization_reload_success"] = True
        row["validity_success"] = _valid_marks(generated, train)
        row["fidelity_score"] = _fidelity_score(train, generated)
        row["notes"] = "candidate passed checks" if row["validity_success"] else "generated invalid marks"
    except Exception as exc:
        row["notes"] = f"{type(exc).__name__}: {exc}"
    return row


def _mark_frame(events: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "side",
        "log_notional",
        "large_print_flag_train",
        "is_interdealer",
        "trade_type",
        "intraday_bucket",
        "weekday",
        "market_activity_regime",
    ]
    present = [column for column in columns if column in events.columns]
    frame = events.loc[:, present].copy()
    for column in frame.columns:
        if frame[column].dtype.name == "category":
            frame[column] = frame[column].astype(str)
    return frame.dropna().reset_index(drop=True)


def _valid_marks(generated: pd.DataFrame, train: pd.DataFrame) -> bool:
    if generated.empty:
        return False
    if set(train.columns).difference(generated.columns):
        return False
    for column in train.columns:
        if pd.api.types.is_numeric_dtype(train[column]):
            values = pd.to_numeric(generated[column], errors="coerce")
            if values.isna().any() or not np.isfinite(values).all():
                return False
        else:
            allowed = set(train[column].dropna().astype(str).unique())
            produced = set(generated[column].dropna().astype(str).unique())
            if not produced.issubset(allowed):
                return False
    return True


def _fidelity_score(train: pd.DataFrame, generated: pd.DataFrame) -> float:
    score = 0.0
    count = 0
    for column in train.columns:
        if column not in generated:
            continue
        if pd.api.types.is_numeric_dtype(train[column]):
            score += abs(float(pd.to_numeric(train[column]).mean()) - float(pd.to_numeric(generated[column], errors="coerce").mean()))
        else:
            left = train[column].astype(str).value_counts(normalize=True)
            right = generated[column].astype(str).value_counts(normalize=True)
            score += float((left.subtract(right, fill_value=0).abs().sum()) / 2.0)
        count += 1
    return score / max(count, 1)


def _fallback_score(events: pd.DataFrame) -> float:
    frame = _mark_frame(events)
    if frame.empty:
        return 0.0
    sample = frame.sample(n=min(len(frame), 500), replace=len(frame) < 500, random_state=0).reset_index(drop=True)
    return _fidelity_score(frame.head(min(len(frame), 2500)), sample)
