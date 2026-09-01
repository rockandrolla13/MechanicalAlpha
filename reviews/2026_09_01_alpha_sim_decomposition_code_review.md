# File-Level Code Review

**Project:** MechanicalAlpha
**Date:** 2026-09-01
**Scope:** Current codebase, reviewed for simulator/alpha decomposability
**Fixed point:** No diff fixed point supplied. This is a file-level review of current `HEAD`, not a patch review.

## Standards Findings

### CR-DEP-001: `bondalpha.cli` imports simulator configuration and utilities

Evidence: `bond_alpha/src/bondalpha/cli.py:28-30`

```text
from bondsim.config import load_config as load_bondsim_config
from bondsim.io import write_json, write_parquet
from bondsim.utils.hashing import file_sha256, stable_json_hash
```

Why it matters: The alpha CLI cannot be used as alpha-only code without installing simulator code.

Recommended fix: Move shared I/O/hash functions out of `bondsim`; move `blinded-workflow` command out of `bondalpha.cli`.

### CR-DEP-002: `bondalpha.freeze` depends on simulator I/O

Evidence: `bond_alpha/src/bondalpha/freeze.py:13-14`

Why it matters: Freezing alpha specs is alpha-domain behavior. It should not require simulator package imports.

Recommended fix: Import hash and JSON writers from a neutral shared module.

### CR-DEP-003: `bondalpha.blinded_gate4` depends on simulator I/O

Evidence: `bond_alpha/src/bondalpha/blinded_gate4.py:32-33`

Why it matters: Blinded evaluation should consume released public data and frozen alpha specs. It should not import simulator code.

Recommended fix: Move `write_json`, `write_parquet`, and hashing into alpha-owned or shared primitives.

### CR-BND-001: `bondalpha.workflow` owns end-to-end Gate 4 orchestration

Evidence: `bond_alpha/src/bondalpha/workflow.py:12-15` and `bond_alpha/src/bondalpha/workflow.py:31-55`.

Why it matters: This is bridge code, not alpha code. It verifies Gate 4, runs/attaches Gate 4, freezes alpha, releases public data, and evaluates blind.

Recommended fix: Move this module to a neutral orchestration package or simulator-side command.

### CR-BND-002: `mechanical_alpha.data.synthetic` bakes simulator partition layout into alpha code

Evidence: `bond_alpha/src/mechanical_alpha/data/synthetic.py:22-32`

Why it matters: It is useful today, but it means alpha code knows simulator output layout.

Recommended fix: Keep it as an optional adapter named `synthetic_public_adapter`, or move simulator-specific layout handling out of the core alpha package.

### CR-DRY-001: Forbidden truth column policy is repeated

Evidence:

- `bond_alpha/src/mechanical_alpha/schema.py:104-122`
- `bond_alpha/src/bondalpha/access_guard.py:10-19`
- `bond_alpha/src/bondsim/outputs.py`

Why it matters: Public/truth separation is a safety invariant. It should have one source of truth.

Recommended fix: Define the policy once in a shared public-contract module.

### CR-ABS-001: `bond_alpha/pyproject.toml` packages everything together

Evidence: `bond_alpha/pyproject.toml:21-24` and `bond_alpha/pyproject.toml:38-40`.

Why it matters: Packaging currently reinforces the code coupling.

Recommended fix: After import cleanup, split packaging or add an alpha-only install path.

## Spec Findings

### CR-SPEC-001: The user wants portable alpha code, but current alpha factory imports simulator code

Evidence: `bondalpha` imports `bondsim` in CLI, workflow, freeze, and blinded evaluation.

Impact: The user cannot clone or install just alpha code without pulling simulator code.

### CR-SPEC-002: Gate blindness is mostly enforced, but the enforcement code is split

Evidence: `bondalpha.access_guard` blocks truth paths and columns, while simulator modules define separate forbidden public columns.

Impact: The safety rule is correct in intent, but harder to audit.

### CR-SPEC-003: Standalone alpha formula files are in good shape

Evidence: `bond_alpha/src/mechanical_alpha/alphas/*.py` expose `describe()` and `compute()` style functions; `registry.py` is an index.

Impact: This is the part to preserve. Do not replace it with a heavy factor framework.

## Handoff

Findings to consolidate:

- CR-DEP-001
- CR-DEP-002
- CR-DEP-003
- CR-BND-001
- CR-BND-002
- CR-DRY-001
- CR-ABS-001
- CR-SPEC-001
- CR-SPEC-002
- CR-SPEC-003

Worst standards issue: `bondalpha` imports `bondsim` in core alpha workflows.

Worst spec issue: alpha code is not yet cleanly cloneable without simulator code.
