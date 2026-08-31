# Plan: gate4-alpha-workstreams

**Integration branch:** orch/integration

Build two quarantined workstreams without alpha evaluation against Gate 4:

- Gate 4 production generation path only.
- Alpha Factory Gate 3 public-data development only.

The Gate 4 workstream must not release public data to alpha development.
The alpha workstream must not inspect or read truth files.

## Phase 1: Parallel Implementation

| # | Task | Files | Depends | Agent | Category | Status | Evidence |
|---|------|-------|---------|-------|----------|--------|----------|
| 1.1 | Implement Gate 4 production-generation core with RUNNING to COMPLETE state, quarantined public/truth roots, canonical content hashes, frozen-calibration checksum verification, and structural/liquidity validation artifacts. Do not run alpha evaluation. | src/bondsim/gate4_generation.py, configs/gate4_production.yaml, tests/test_gate4_generation.py |  | codex | codegen | PENDING |  |
| 1.2 | Implement Alpha Factory public-data contracts, strict truth-access controls, separate target schemas, time splits, costs, metrics, and Gate 3 inspection/build/research/validate report writers. Use Gate 3 public data only. | src/bondalpha/access_control.py, src/bondalpha/schemas.py, src/bondalpha/costs.py, src/bondalpha/metrics.py, src/bondalpha/reporting.py, configs/alpha/base.yaml, tests/alpha/test_alpha_public_contracts.py |  | opencode | codegen | PENDING |  |
| 1.3 | Implement standalone Alpha Factory family modules for reversal, flow persistence, lead-lag, relative value, and composite selection scaffolding. Do not freeze alpha specs and do not read truth. | src/bondalpha/reversal/, src/bondalpha/flow/, src/bondalpha/leadlag/, src/bondalpha/relative_value/, src/bondalpha/composite/, tests/alpha/test_alpha_family_outputs.py |  | codex | codegen | PENDING |  |
| 1.4 | Implement Alpha Factory public dataset loading and label construction for future clean-price move, issuer-residual move, next-event side, and future signed flow. Keep targets separate. | src/bondalpha/public_datasets.py, src/bondalpha/target_labels.py, tests/alpha/test_alpha_targets.py |  | gemini | codegen | PENDING |  |

## Phase 2: CLI Wiring And Workflow Tests

| # | Task | Files | Depends | Agent | Category | Status | Evidence |
|---|------|-------|---------|-------|----------|--------|----------|
| 2.1 | Wire CLI commands for Gate 4 production generation and Alpha Factory inspect, build-features, research, and validate. Add command tests. | src/bondsim/cli.py, src/bondalpha/cli.py, tests/test_gate4_generation_cli.py, tests/alpha/test_alpha_cli_commands.py | 1.1, 1.2, 1.3, 1.4 | codex | codegen | PENDING |  |

## Phase 3: Review And Documentation

| # | Task | Files | Depends | Agent | Category | Status | Evidence |
|---|------|-------|---------|-------|----------|--------|----------|
| 3.1 | Run a focused implementation review against the two supplied workstream prompts. Verify no alpha code reads Gate 4 truth and no Gate 4 generation release occurs. | reviews/gate4_alpha_workstreams_review.md | 2.1 | opencode | review | PENDING |  |
