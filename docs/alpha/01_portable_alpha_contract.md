# Portable Alpha Contract

Date: 2026-08-30

Purpose: make the alpha code portable to a work machine with real data.

## Rule

Alpha factors consume one object:

```text
AlphaInputBundle
```

They do not query databases.

They do not read simulator truth.

They do not know raw vendor column names.

## Current Package

The portable package is:

```text
bond_alpha/src/mechanical_alpha
```

The simulator package remains:

```text
bond_alpha/src/bondsim
```

## Work-Machine Transition

On this machine:

```text
mechanical_alpha.data.marketdb_trace
```

loads the local `marketdb.trace` sample.

On the work machine, add a new adapter:

```text
mechanical_alpha.data.work_realdata
```

That adapter should return the same `AlphaInputBundle`.

No factor should change.

## Canonical Tables

Required tables:

- `bonds`
- `events`

Optional tables:

- `quotes`
- `fair_values`
- `rfqs`
- `external_factors`

Each field has an availability status:

- `directly_available`
- `derivable`
- `partially_available`
- `unavailable`
- `ambiguous`

## Side Policy

The project requires dealer perspective:

```text
client sells to dealer = +1
client buys from dealer = -1
```

The local TRACE adapter currently marks side as ambiguous.

This is intentional.

The work-machine adapter should normalize side once.

After that, factors should not flip signs.

## Source Separation

Forbidden public columns include:

- source security identifiers
- client identifiers
- dealer identifiers
- truth labels
- latent simulator state

The bundle validator rejects these fields.

## First Supported Flow

```text
real data or synthetic data
  -> source adapter
  -> AlphaInputBundle
  -> availability registry
  -> factor registry
  -> factor implementations
```

The current implementation stops at the registry and contract layer.

Production factor formulas are intentionally not implemented yet.
