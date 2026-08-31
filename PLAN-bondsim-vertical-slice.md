# Plan: bondsim vertical slice

**Created:** 2026-08-30
**Workflow:** W1 build
**Source:** ideate + deepening + design-it-twice
**Target directory:** `/media/ak/10E1026C4FA6006E/GitRepos/MechanicalAlpha/bond_alpha`

## Objective

Build a usable vertical slice of a corporate-bond synthetic market simulator.
It must inspect real local data, canonicalize events, simulate smoke scenarios, keep public data separate from truth data, and validate the result.

## Pre-Execution Snapshot

- **Architecture review score:** not run
- **File count:** 13 tracked candidate files under `bond_alpha`
- **Total lines:** not material
- **Test status:** existing acquisition tests previously passed

## Phases

### Phase 1: Discovery And Configuration

| # | Step | Source | Status | Evidence | Notes |
|---|------|--------|--------|----------|-------|
| 1.1 | Inspect environment, SynthCity, and marketdb TRACE | design path | DONE | 2026-08-30T01:40:00 | SynthCity registry import fails; marketdb TRACE available |
| 1.2 | Add base scenario configuration | design path | DONE | 2026-08-30T02:05:00 | Added base and scenario YAML files |
| 1.3 | Generate discovery reports and column mapping | design path | DONE | 2026-08-30T02:12:00 | `reports/data_discovery.md`, `reports/data_profile.json`, `configs/column_mapping.generated.yaml` |

### Phase 2: Canonical Data

| # | Step | Source | Status | Evidence | Notes |
|---|------|--------|--------|----------|-------|
| 2.1 | Implement canonical event and bond preparation | design path | DONE | 2026-08-30T02:15:00 | `data/processed/events.parquet`, `data/processed/bonds.parquet` |
| 2.2 | Add temporal split and liquidity summaries | design path | DONE | 2026-08-30T02:15:00 | split dates in preparation manifest; liquidity in scenario manifests |

### Phase 3: Simulation

| # | Step | Source | Status | Evidence | Notes |
|---|------|--------|--------|----------|-------|
| 3.1 | Implement deterministic universe and liquidity mapping | design path | DONE | 2026-08-30T02:20:00 | `src/bondsim/universe.py`, `src/bondsim/liquidity.py` |
| 3.2 | Implement sparse Hawkes cluster simulation | design path | DONE | 2026-08-30T02:20:00 | `src/bondsim/hawkes/graph.py`, `src/bondsim/hawkes/simulate.py` |
| 3.3 | Implement empirical/SynthCity mark seam | design path | DONE | 2026-08-30T02:20:00 | `src/bondsim/marks/fallback.py`, `src/bondsim/marks/synthcity_adapter.py` |
| 3.4 | Implement price states, planted effects, scenarios, and truth ledger | design path | DONE | 2026-08-30T02:22:00 | `src/bondsim/prices/engine.py`, `src/bondsim/truth.py` |

### Phase 4: Validation And Reports

| # | Step | Source | Status | Evidence | Notes |
|---|------|--------|--------|----------|-------|
| 4.1 | Implement structural validation and report generation | design path | DONE | 2026-08-30T02:30:00 | `src/bondsim/validation/report.py`, required report files |
| 4.2 | Run smoke pipeline and tests | design path | DONE | 2026-08-30T02:36:00 | 7 tests passed; six smoke scenarios passed validation; controlled_all medium passed validation |

## Invariants

| Invariant | Check Command | Status |
|-----------|---------------|--------|
| package-imports | `PYTHONPATH=src python -c "import bondsim"` | |
| smoke-tests-pass | `python -m pytest -q` | PASS |
| smoke-pipeline-runs | `python -m bondsim pipeline --config configs/controlled_all.yaml --mode smoke --force` | PASS |

## Verification Criteria

- [x] Discovery report exists.
- [x] Canonical processed bonds and events exist.
- [x] Smoke public synthetic trades and private truth exist.
- [x] Public schema excludes source identifiers and truth columns.
- [x] Tests pass.

## Execution Log

- 2026-08-30T01:40:00 — Plan created and execution started without approval checkpoint per user instruction.
- 2026-08-30T02:12:00 — Discovery and generated mapping completed from `marketdb.trace`.
- 2026-08-30T02:15:00 — Canonical processed events and bonds written.
- 2026-08-30T02:25:00 — First controlled smoke pipeline passed.
- 2026-08-30T02:32:00 — All six smoke scenarios generated and structurally validated.
- 2026-08-30T02:36:00 — Controlled-all medium run generated 100 bonds and 41,826 events; validation passed.
- 2026-08-30T02:38:00 — Final tests passed: 7 passed.
