# Portable Alpha Package

This note defines the code that can move to a work machine when only alpha
research and evaluation are needed.

## Move These Paths

- `src/mechanical_alpha/`
- `src/bondalpha/`
- `configs/alphas/`
- `configs/alpha/`
- `docs/alpha/`
- alpha-related tests under `tests/alpha/`
- shared alpha contract tests under `tests/test_public_*` and `tests/test_package_boundaries.py`

## Do Not Move These Paths For Alpha-Only Work

- `src/bondsim/`
- `data/synthetic_truth/`
- `data/quarantine/gate4_truth/`
- simulator calibration truth files
- simulator planted-effect parameter files

## Boundary Rule

Alpha code may load public canonical tables.

Alpha code may not import simulator internals.

The only exception is the temporary compatibility shim:

- `src/bondalpha/workflow.py`

New code should call the simulator-owned bridge instead:

- `src/bondsim/alpha_workflow.py`

## Public Data Contract

The portable alpha contract is `mechanical_alpha.contracts.AlphaInputBundle`.

Required public tables are:

- `bonds`
- `events`

Optional public tables are:

- `quotes`
- `fair_values`
- `rfqs`
- `external_factors`

Every table is validated against the public/truth guard policy in
`mechanical_alpha.public_policy`.

## Work-Machine Migration

On the work machine, create an adapter that maps local public data to
`AlphaInputBundle`.

The adapter should document:

- source table names;
- timestamp semantics;
- side convention;
- price units;
- notional units;
- DV01 and CR01 units where available;
- missing fields;
- point-in-time limitations.

The alpha files should not change when the adapter changes.

## Quick Boundary Check

From `bond_alpha/`, run:

```bash
python -m pytest tests/test_package_boundaries.py -q
```

The test fails if alpha code imports simulator internals outside the temporary
compatibility shim.
