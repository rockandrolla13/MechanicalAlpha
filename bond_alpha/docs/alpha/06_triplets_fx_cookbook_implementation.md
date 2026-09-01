# Triplets And FX Cookbook Implementation

## What Was Added

The cookbook implementation lives inside the existing portable alpha package:

```text
src/mechanical_alpha/
├── triplets/
├── fx_cookbook/
└── alphas/T1_triplet_momentum_reversal.py
```

No second registry, runner, report system, or data loader was added.
The existing `AlphaInputBundle` remains the only public-data input contract.

## Registered Names

- `T1`: triplet momentum/reversal alpha entry point.
- `FX_MOM`: implemented cookbook price-momentum primitives.
- `FX_CARRY`: blocked pending `CARRY-001`, `CARRY-002`, `CARRY-003`.
- `FX_VALUE`: blocked pending `VALUE-001`.
- `RATES_SPILLOVER`: blocked until point-in-time rates or curve-factor inputs are supplied.
- `COFFEE_DTCC`: blocked pending `COFFEE-001`, `COFFEE-002` and positioning data.
- `CFTC_CONT`: blocked until CFTC COT data are supplied.
- `CFTC_REV`: blocked pending `CFTC-R-001` and CFTC COT data.

## How To Add Another Standalone Alpha

1. Create one file under `src/mechanical_alpha/alphas/`.
2. Expose `describe()` and `compute(bundle, ...)`.
3. Consume only `AlphaInputBundle` public tables.
4. Put reusable math in a narrow shared module only if another alpha needs it.
5. Add one `AlphaFile` row in `src/mechanical_alpha/registry.py`.
6. Add tests with hand-calculated fixtures.

Do not read simulator truth paths, Gate 4 quarantined truth, source identifiers, or raw proprietary categories.

## Canonical Commands

Run all tests:

```bash
conda run -n MechanicalAlpha python -m pytest -q
```

Check alpha input availability on a public synthetic scenario:

```bash
python -m mechanical_alpha.cli availability --synthetic-root data/synthetic/scenario=controlled_all
```

