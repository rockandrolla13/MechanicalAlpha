# Plan: gate4-alpha-implementation

**Integration branch:** orch/integration

Build the implementation portions of the quarantined Gate 4 and Alpha Factory
workstreams. The final implementation review is intentionally kept outside this
headless conductor plan because the installed review skill has an interactive
checkpoint gate.

The Gate 4 workstream must not release public data to alpha development.
The alpha workstream must not inspect or read truth files.

## Phase 1: Parallel Implementation

| # | Task | Files | Depends | Agent | Category | Status | Evidence |
|---|------|-------|---------|-------|----------|--------|----------|
| 1.1 | Implement Gate 4 production-generation core with RUNNING to COMPLETE state, quarantined public/truth roots, canonical content hashes, frozen-calibration checksum verification, and structural/liquidity validation artifacts. Do not run alpha evaluation. | src/bondsim/gate4_generation.py, configs/gate4_production.yaml, tests/test_gate4_generation.py |  | codex | codegen | FAILED | codex: produced no changes [kept: orch/failed/20260831-025352-1169760/task-1-1] |
| 1.2 | Implement Alpha Factory public-data contracts, strict truth-access controls, separate target schemas, time splits, costs, metrics, and Gate 3 inspection/build/research/validate report writers. Use Gate 3 public data only. | src/bondalpha/access_control.py, src/bondalpha/schemas.py, src/bondalpha/costs.py, src/bondalpha/metrics.py, src/bondalpha/reporting.py, configs/alpha/base.yaml, tests/alpha/test_alpha_public_contracts.py |  | opencode | codegen | FAILED | opencode: tests FAILED: 1 error in 0.07s [log: failed-1.2.log] [kept: orch/failed/20260831-025352-1169760/task-1-2] |
| 1.3 | Implement standalone Alpha Factory family modules for reversal, flow persistence, lead-lag, relative value, and composite selection scaffolding. Do not freeze alpha specs and do not read truth. | src/bondalpha/reversal/, src/bondalpha/flow/, src/bondalpha/leadlag/, src/bondalpha/relative_value/, src/bondalpha/composite/, tests/alpha/test_alpha_family_outputs.py |  | codex | codegen | COMPLETED | codex; tests OK (1 passed in 0.01s) [files: src/bondalpha/composite/__init__.py, src/bondalpha/composite/__pycache__/__init__.cpython-312.pyc, src/bondalpha/composite/__pycache__/selection.cpython-312.pyc, src/bondalpha/composite/selection.py, src/bondalpha/flow/__init__.py, src/bondalpha/flow/__pycache__/__init__.cpython-312.pyc, src/bondalpha/flow/__pycache__/family.cpython-312.pyc, src/bondalpha/flow/family.py, src/bondalpha/leadlag/__init__.py, src/bondalpha/leadlag/__pycache__/__init__.cpython-312.pyc, src/bondalpha/leadlag/__pycache__/family.cpython-312.pyc, src/bondalpha/leadlag/family.py, +10 more] [wrote unclaimed: tests/alpha/__pycache__/test_alpha_family_outputs.cpython-312-pytest-9.0.2.pyc] [integration OK (1 passed in 0.01s); verified in 1.1s] |
| 1.4 | Implement Alpha Factory public dataset loading and label construction for future clean-price move, issuer-residual move, next-event side, and future signed flow. Keep targets separate. | src/bondalpha/public_datasets.py, src/bondalpha/target_labels.py, tests/alpha/test_alpha_targets.py |  | gemini | codegen | FAILED | gemini: exit 41: Update your environment and try again (no reload needed if using .env)! |

## Phase 2: CLI Wiring And Workflow Tests

| # | Task | Files | Depends | Agent | Category | Status | Evidence |
|---|------|-------|---------|-------|----------|--------|----------|
| 2.1 | Wire CLI commands for Gate 4 production generation and Alpha Factory inspect, build-features, research, and validate. Add command tests. | src/bondsim/cli.py, src/bondalpha/cli.py, tests/test_gate4_generation_cli.py, tests/alpha/test_alpha_cli_commands.py | 1.1, 1.2, 1.3, 1.4 | codex | codegen | BLOCKED | dependency unmet |
