"""Deep pipeline modules for discovery, preparation, fitting, simulation, and validation."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from bondsim import __version__
from bondsim.activity import daily_activity_multipliers, session_calendar
from bondsim.calibration.frozen import load_frozen_calibration
from bondsim.config import BondSimConfig, write_resolved_config
from bondsim.discovery import DiscoveryResult, run_discovery
from bondsim.hawkes.graph import HawkesGraph, build_hawkes_graph
from bondsim.hawkes.simulate import simulate_session_clock
from bondsim.io import manifest_for_files, write_json, write_parquet
from bondsim.liquidity import realized_rate_summary
from bondsim.marks.fallback import EmpiricalMarkSampler
from bondsim.marks.synthcity_adapter import MarkModelSelection, run_mark_tournament
from bondsim.outputs import assert_public_schema_is_clean, write_monthly_partitions
from bondsim.preprocess import PreparedDataManifest, prepare_data
from bondsim.prices.engine import PriceEngine
from bondsim.scenarios import flags_for
from bondsim.schema import PUBLIC_TRADE_COLUMNS, TRUTH_COLUMNS
from bondsim.truth import write_combined_truth_markdown, write_truth_markdown, write_truth_parameters
from bondsim.universe import build_universe
from bondsim.utils.hashing import stable_json_hash
from bondsim.utils.seeds import SeedBank
from bondsim.validation.report import validate_outputs, write_fidelity_plots, write_reports
from bondsim.validation.recovery import run_recovery_checks


@dataclass(frozen=True)
class SimulationManifest:
    scenario: str
    mode: str
    public_path: Path
    truth_path: Path
    manifest_path: Path
    validation: dict[str, object]


class DiscoveryPipeline:
    def __init__(self, config: BondSimConfig):
        self.config = config

    def run(self) -> DiscoveryResult:
        return run_discovery(self.config)


class PreparationPipeline:
    def __init__(self, config: BondSimConfig):
        self.config = config

    def run(self, mode: str = "full") -> PreparedDataManifest:
        return prepare_data(self.config, mode=mode)


class FitPipeline:
    def __init__(self, config: BondSimConfig):
        self.config = config

    def run(self, mode: str = "quick") -> MarkModelSelection:
        processed = self.config.paths.processed_root
        if not (processed / "events.parquet").exists():
            PreparationPipeline(self.config).run(mode="smoke" if mode == "quick" else mode)
        events = pd.read_parquet(processed / "events.parquet")
        train_events = _training_events(events)
        candidates = self.config.marks.quick_candidates if mode in {"quick", "smoke"} else self.config.marks.synthcity_candidates
        return run_mark_tournament(
            train_events,
            candidates,
            self.config.paths.report_root,
            self.config.paths.model_root / "marks",
        )


class SimulationPipeline:
    def __init__(self, config: BondSimConfig):
        self.config = config
        self.seed_bank = SeedBank.create(config.project.master_seed)

    def run(self, mode: str = "smoke", scenario: str | None = None, force: bool = False) -> SimulationManifest:
        scenario_name = scenario or self.config.scenario
        flags = flags_for(scenario_name)
        write_resolved_config(self.config)
        processed = self.config.paths.processed_root
        if not (processed / "events.parquet").exists() or not (processed / "bonds.parquet").exists():
            PreparationPipeline(self.config).run(mode=mode)
        real_events = pd.read_parquet(processed / "events.parquet")
        real_bonds = pd.read_parquet(processed / "bonds.parquet")
        train_events = _training_events(real_events)
        universe = build_universe(real_bonds, self.config, self.seed_bank.rng("universe"), mode)
        graph = build_hawkes_graph(universe, self.config, flags)
        branching_mass = graph.same_side_mass + graph.opposite_side_mass + graph.leader_follower_mass
        branching_adjustment = 1.0 / max(1e-6, 1.0 - branching_mass)
        desired_rates = universe["target_events_per_day"].copy()
        universe["target_events_per_day"] = desired_rates / branching_adjustment
        universe["target_events_per_day"] = _calibrate_event_rate_baselines(
            universe,
            graph,
            desired_rates,
            self.config,
            int(self.seed_bank.streams["output"]),
        )
        mark_selection = _mark_selection_for_run(self.config, mode)
        sampler = EmpiricalMarkSampler(train_events)
        if mode == "smoke":
            n_sessions = self.config.simulation.smoke_sessions
        elif mode == "medium":
            n_sessions = self.config.simulation.medium_sessions
        else:
            n_sessions = self.config.simulation.n_sessions
        sessions = session_calendar(str(real_events["session_date"].min()), n_sessions)
        activity = daily_activity_multipliers(n_sessions, self.seed_bank.rng("activity"))
        price_engine = PriceEngine(universe, self.config, flags, self.seed_bank.rng("ou"))
        public_rows: list[dict[str, object]] = []
        truth_rows: list[dict[str, object]] = []
        mark_rng = self.seed_bank.rng("marks")
        immigrant_rng = self.seed_bank.rng("hawkes_immigrants")
        offspring_rng = self.seed_bank.rng("hawkes_offspring")
        for session_idx, session in enumerate(sessions):
            clock_events = simulate_session_clock(
                universe,
                graph,
                session_idx,
                float(activity[session_idx]),
                immigrant_rng,
                offspring_rng,
                self.config.simulation.max_events_per_session_safety,
            )
            for event_idx, clock_event in enumerate(clock_events):
                event_id = f"{scenario_name}_{session_idx:04d}_{event_idx:06d}"
                mark = sampler.sample(clock_event.side, mark_rng)
                public, truth = price_engine.price_event(clock_event, mark, event_id)
                timestamp = pd.Timestamp(session) + pd.Timedelta(hours=9, minutes=30) + pd.Timedelta(clock_event.seconds, unit="s")
                public.update(
                    {
                        "timestamp_utc": timestamp,
                        "session_date": str(pd.Timestamp(session).date()),
                        "synthetic_bond_id": clock_event.synthetic_bond_id,
                        "synthetic_issuer_id": clock_event.synthetic_issuer_id,
                    }
                )
                truth.update(
                    {
                        "scenario": scenario_name,
                        "timestamp_utc": timestamp,
                        "session_date": str(pd.Timestamp(session).date()),
                        "hawkes_cluster_id": clock_event.cluster_id,
                        "hawkes_parent_event_id": clock_event.parent_event_id,
                        "hawkes_generation": clock_event.generation,
                        "hawkes_edge_class": clock_event.edge_class,
                        "is_immigrant": clock_event.is_immigrant,
                    }
                )
                public_rows.append(public)
                truth_rows.append(truth)
        trades = pd.DataFrame(public_rows).loc[:, PUBLIC_TRADE_COLUMNS]
        truth = pd.DataFrame(truth_rows).loc[:, TRUTH_COLUMNS]
        assert_public_schema_is_clean(trades.columns)
        public_root = self.config.paths.synthetic_root / f"scenario={scenario_name}"
        truth_root = self.config.paths.truth_root / f"scenario={scenario_name}"
        if public_root.exists() and not force and (public_root / "manifest.json").exists():
            raise FileExistsError(f"Completed scenario exists: {public_root}. Use --force.")
        if force:
            shutil.rmtree(public_root, ignore_errors=True)
            shutil.rmtree(truth_root, ignore_errors=True)
        bonds_path = write_parquet(universe.drop(columns=["source_bond_id", "source_issuer_id"], errors="ignore"), public_root / "bonds.parquet")
        public_specs = write_monthly_partitions(
            trades,
            public_root,
            "trades",
            compression=self.config.simulation.parquet_compression,
        )
        truth_specs = write_monthly_partitions(
            truth,
            truth_root,
            "event_truth",
            compression=self.config.simulation.parquet_compression,
        )
        if not public_specs or not truth_specs:
            raise RuntimeError(f"scenario {scenario_name} produced no partitioned output")
        public_path = public_specs[0].path
        truth_path = truth_specs[0].path
        liquidity_summary = realized_rate_summary(trades, n_sessions)
        config_hash = stable_json_hash(self.config.model_dump(mode="json"))
        truth_payload = write_truth_parameters(self.config.paths.truth_root, scenario_name, graph, mark_selection, liquidity_summary, config_hash)
        write_truth_markdown(Path("data") / "SYNTHETIC_TRUTH.md", truth_payload)
        validation = validate_outputs(trades, truth, universe, self.config, scenario_name, mode)
        recovery = run_recovery_checks(trades, truth)
        validation["recovery"] = recovery
        manifest = manifest_for_files(
            [spec.path for spec in public_specs] + [spec.path for spec in truth_specs] + [bonds_path],
            {
                "simulator_version": __version__,
                "scenario": scenario_name,
                "mode": mode,
                "rows": {"public": len(trades), "truth": len(truth), "bonds": len(universe)},
                "partitions": {
                    "public": [spec.__dict__ for spec in public_specs],
                    "truth": [spec.__dict__ for spec in truth_specs],
                },
                "liquidity": liquidity_summary,
                "recovery": recovery,
                "hawkes": graph.__dict__,
                "config": self.config.model_dump(mode="json"),
            },
        )
        manifest_path = write_json(manifest, public_root / "manifest.json")
        write_json(manifest, truth_root / "manifest.json")
        write_reports(
            self.config.paths.report_root,
            validation,
            {
                "git_commit": _git_commit(),
                "truth": truth_payload,
                "hawkes": graph.__dict__,
                "prices": {"route": self.config.prices.fair_value_route, "price_convention": "public trade price uses pre-trade midpoint plus concession/noise"},
                "recovery": recovery,
            },
        )
        write_fidelity_plots(self.config.paths.report_root, trades, truth)
        if not validation["passed"]:
            raise RuntimeError(f"Validation failed: {validation['failures']}")
        return SimulationManifest(scenario_name, mode, public_path, truth_path, manifest_path, validation)


class ValidationPipeline:
    def __init__(self, config: BondSimConfig):
        self.config = config

    def run(self, mode: str = "smoke", scenario: str | None = None) -> dict[str, object]:
        scenario_name = scenario or self.config.scenario
        public_root = self.config.paths.synthetic_root / f"scenario={scenario_name}"
        truth_root = self.config.paths.truth_root / f"scenario={scenario_name}"
        trades = _read_partitioned(public_root / "trades")
        truth = _read_partitioned(truth_root / "event_truth")
        bonds = pd.read_parquet(public_root / "bonds.parquet")
        result = validate_outputs(trades, truth, bonds, self.config, scenario_name, mode)
        result["recovery"] = run_recovery_checks(trades, truth)
        write_json(result, self.config.paths.report_root / "validation_summary.json")
        return result


def run_full_pipeline(config: BondSimConfig, mode: str, force: bool) -> list[SimulationManifest]:
    DiscoveryPipeline(config).run()
    processed = config.paths.processed_root
    if not (processed / "events.parquet").exists() or not (processed / "bonds.parquet").exists():
        PreparationPipeline(config).run(mode=mode)
    scenarios = ["calibrated_realism", "controlled_all", "controlled_null"] if mode == "smoke" else [config.scenario]
    results = [SimulationPipeline(config).run(mode=mode, scenario=scenario, force=force) for scenario in scenarios]
    payloads = []
    for scenario in scenarios:
        path = config.paths.truth_root / f"scenario={scenario}" / "parameter_truth.json"
        if path.exists():
            import json

            payloads.append(json.loads(path.read_text()))
    if payloads:
        write_combined_truth_markdown(Path("data") / "SYNTHETIC_TRUTH.md", payloads)
        _write_combined_smoke_reports(config, scenarios, payloads)
    return results


def _training_events(events: pd.DataFrame) -> pd.DataFrame:
    sessions = sorted(events["session_date"].unique())
    cutoff = sessions[max(0, int(len(sessions) * 0.70) - 1)]
    return events[events["session_date"] <= cutoff].copy()


def _mark_selection_for_run(config: BondSimConfig, mode: str) -> MarkModelSelection:
    if config.frozen_calibration_id:
        frozen = load_frozen_calibration(config.frozen_calibration_id, config.paths.model_root)
        selected = frozen.selected_models
        return MarkModelSelection(
            selected=str(selected.get("selected", "empirical_fallback")),
            synthcity_version=str(selected.get("synthcity_version", "frozen")),
            available_plugins=list(selected.get("available_plugins", [])),
            candidates=list(selected.get("candidates", [])),
            failure=selected.get("failure"),
        )
    return FitPipeline(config).run("quick" if mode in {"smoke", "medium"} else "full")


def _calibrate_event_rate_baselines(
    universe: pd.DataFrame,
    graph: HawkesGraph,
    desired_rates: pd.Series,
    config: BondSimConfig,
    seed: int,
) -> pd.Series:
    """Calibrate immigrant baselines to desired total event rates using clock-only pilots."""

    calibrated = universe["target_events_per_day"].astype(float).copy()
    damping = float(config.liquidity.calibration_damping)
    pilot_sessions = int(config.liquidity.pilot_sessions)
    iterations = int(config.liquidity.calibration_iterations)
    max_rate = float(config.liquidity.maximum_events_per_day)
    bond_ids = universe["synthetic_bond_id"].astype(str).to_numpy()
    for iteration in range(iterations):
        pilot = universe.copy()
        pilot["target_events_per_day"] = calibrated
        counts = pd.Series(0.0, index=bond_ids)
        root = np.random.SeedSequence([int(seed), iteration])
        activity_rng, immigrant_rng, offspring_rng = [np.random.default_rng(child) for child in root.spawn(3)]
        activity = daily_activity_multipliers(pilot_sessions, activity_rng)
        for session_idx in range(pilot_sessions):
            events = simulate_session_clock(
                pilot,
                graph,
                session_idx,
                float(activity[session_idx]),
                immigrant_rng,
                offspring_rng,
                config.simulation.max_events_per_session_safety,
            )
            if events:
                session_counts = pd.Series([event.synthetic_bond_id for event in events]).value_counts()
                counts = counts.add(session_counts, fill_value=0.0)
        realized = counts.reindex(bond_ids).fillna(0.0).to_numpy() / max(pilot_sessions, 1)
        desired = desired_rates.to_numpy(dtype=float)
        ratio = desired / np.maximum(realized, 0.05)
        calibrated = pd.Series(
            np.clip(calibrated.to_numpy(dtype=float) * np.power(np.clip(ratio, 0.25, 4.0), damping), 1e-4, max_rate),
            index=universe.index,
        )
    pilot = universe.copy()
    pilot["target_events_per_day"] = calibrated
    counts = pd.Series(0.0, index=bond_ids)
    root = np.random.SeedSequence([int(seed), iterations, 991])
    activity_rng, immigrant_rng, offspring_rng = [np.random.default_rng(child) for child in root.spawn(3)]
    activity = daily_activity_multipliers(pilot_sessions, activity_rng)
    for session_idx in range(pilot_sessions):
        events = simulate_session_clock(
            pilot,
            graph,
            session_idx,
            float(activity[session_idx]),
            immigrant_rng,
            offspring_rng,
            config.simulation.max_events_per_session_safety,
        )
        if events:
            session_counts = pd.Series([event.synthetic_bond_id for event in events]).value_counts()
            counts = counts.add(session_counts, fill_value=0.0)
    realized = counts.reindex(bond_ids).fillna(0.0).to_numpy() / max(pilot_sessions, 1)
    realized_p10 = float(np.quantile(realized, 0.10))
    target_p10 = float(config.liquidity.target_p10_events_per_day)
    if realized_p10 > 0:
        low_tail = desired_rates <= float(np.quantile(desired_rates, 0.25))
        tail_scale = np.clip(target_p10 / realized_p10, 0.50, 1.50)
        adjusted = calibrated.to_numpy(dtype=float)
        adjusted[low_tail.to_numpy(dtype=bool)] *= tail_scale
        calibrated = pd.Series(np.clip(adjusted, 1e-4, max_rate), index=universe.index)
    return calibrated


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _read_partitioned(root: Path) -> pd.DataFrame:
    files = sorted(root.glob("year=*/month=*/part-*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet partitions under {root}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)


def _write_combined_smoke_reports(config: BondSimConfig, scenarios: list[str], payloads: list[dict[str, object]]) -> None:
    import json

    rows = []
    for scenario, payload in zip(scenarios, payloads, strict=False):
        manifest_path = config.paths.synthetic_root / f"scenario={scenario}" / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        rows.append(
            {
                "scenario": scenario,
                "rows": manifest.get("rows", {}),
                "hawkes": payload.get("hawkes", {}),
                "liquidity": payload.get("liquidity_summary", {}),
                "mark_model": payload.get("synthcity", {}).get("selected"),
                "recovery": manifest.get("recovery", {}),
            }
        )
    report_root = config.paths.report_root
    report_root.mkdir(parents=True, exist_ok=True)
    (report_root / "hawkes_fit.md").write_text("# Hawkes Fit\n\n```text\n" + "\n".join(str(row) for row in rows) + "\n```\n")
    (report_root / "positive_controls.md").write_text(
        "# Positive Controls\n\n```text\n" + "\n".join(str(row) for row in rows) + "\n```\n"
    )
    (report_root / "price_model_fit.md").write_text(
        "# Price Model Fit\n\nRoute: `transaction_price_proxy`.\n\n"
        "Public trade price uses pre-trade midpoint plus immediate event impact, side concession, and observation noise.\n"
        "Fair values are issuer-centered price-space random walks because local TRACE lacks vendor fair value, OAS, duration, bid, ask, and mid.\n"
    )
    fidelity = report_root / "fidelity"
    fidelity.mkdir(parents=True, exist_ok=True)
    (fidelity / "summary.md").write_text("# Fidelity Summary\n\n```text\n" + "\n".join(str(row) for row in rows) + "\n```\n")
