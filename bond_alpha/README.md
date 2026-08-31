# bond_alpha

`bond_alpha` is a scaffold for computing and testing corporate-bond alpha factors.

The project is organized around a strict data and factor pipeline. Each stage should consume only files produced by earlier stages or approved external inputs. All feature construction must be as-of safe.

## Pipeline DAG

```text
raw RFQ / tape / market data
  -> acquisition
  -> clean data
  -> bars
  -> factors
  -> fitted models
  -> evaluation
```

## Directories

```text
bond_alpha/
  data/
    raw/      source inputs; do not mutate in place
    clean/    normalized and validated records
    bars/     time, volume, and transaction bars
  factors/    one module per factor family
  estimation/ fitted models and model utilities
  evaluation/ backtests, diagnostics, and reports
tests/         smoke and regression tests
```

## Pipeline Stages

`acquisition`

Loads a canonical trade tape with columns `cusip, ts, price, par_volume, side_flag, contra_party_type`.
The current interchangeable sources are WRDS TRACE Enhanced, FINRA public TRACE CSV-style data, and a synthetic positive-control generator.

`clean-data`

Reads raw inputs and writes validated clean data.

`bars`

Builds time bars, volume bars, and transaction bars from clean data.

`factors`

Computes alpha factors from bars and aligned reference data.

`evaluate`

Evaluates factors and fitted models against forward return horizons.

## Dependency Policy

Core dependencies are limited to:

- pandas
- numpy
- scipy
- statsmodels
- scikit-learn

Polars may be added later for tape processing only.

## Data Sources

`bond_alpha.data.load_tape(source)` is the single acquisition interface.

WRDS TRACE Enhanced expects the caller to pass an authenticated database connection.
It can join TRACE trades to Mergent FISD reference fields such as amount outstanding, rating, maturity, and sector.

FINRA public TRACE can load disseminated CSV-style data.
Public corporate-bond volumes are capped at `5MM+` for investment grade and `1MM+` for non-investment grade.
Those capped values are lower bounds, not exact sizes.

Synthetic data simulates 500 bonds over three years by default.
It plants high-volume reversal, sign persistence, and liquid-to-illiquid issuer lead-lag effects.
See `bond_alpha/data/SYNTHETIC_TRUTH.md`.

## BondSim Commands

The production-shaped simulator lives in `src/bondsim`.
Run commands from this directory.

```bash
conda activate MechanicalAlpha
export PYTHONPATH=src:/media/ak/10E1026C4FA6006E/GitRepos/HFT-in-a-Limit-Order-Book/src

python -m bondsim inspect --config configs/base.yaml
python -m bondsim prepare --config configs/base.yaml --mode smoke
python -m bondsim fit --config configs/base.yaml --mode quick
python -m bondsim simulate --config configs/controlled_all.yaml --mode smoke --force
python -m bondsim validate --config configs/controlled_all.yaml --mode smoke
python -m bondsim pipeline --config configs/controlled_all.yaml --mode smoke --force
```

Smoke mode uses 10 bonds and 20 sessions.
Medium mode uses 100 bonds and 100 sessions.
Full mode is configured for 500 bonds and 756 sessions with streaming-compatible output paths.

Gate 3 is governed by `docs/GATE3_PROMPT.md`.
It must use a frozen Gate 2.5 calibration bundle and must not refit calibration artifacts.

## Portable Alpha Contract

The portable alpha package lives in `src/mechanical_alpha`.
It is separate from `bondsim`.

Factor code should consume `mechanical_alpha.AlphaInputBundle`.
It should not query `marketdb` or simulator truth tables directly.

```bash
conda activate MechanicalAlpha
mechanical-alpha availability \
  --synthetic-root data/synthetic/scenario=controlled_all \
  --output reports/alpha_availability_controlled_all.csv
```

On a work machine with real data, add a source adapter that returns the same `AlphaInputBundle`.
The factor code should not need to change.
