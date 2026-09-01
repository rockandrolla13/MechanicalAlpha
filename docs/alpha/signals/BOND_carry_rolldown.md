# BOND_CARRY_ROLLDOWN

## Purpose

This alpha computes bond carry, roll-down, relative value, and total expected price contribution from a point-in-time par-adjusted spread curve.

It follows Richard Martin, *The credit spread curve. I: Fundamental concepts, fitting, par-adjusted spread, and expected return*, arXiv:2201.01330v3.

## Required Input

The alpha consumes public `external_factors` rows with:

- `timestamp`
- `publication_timestamp`, when available
- `factor_id = par_adjusted_spread_curve`
- `bond_id`
- `issuer_id`
- `curve_id`
- `tenor_years`
- `years_to_maturity`
- `par_adjusted_spread`
- `model_par_spread`
- `risky_pv01`
- `coupon_minus_riskfree`

The work-machine migration should map the local computed curve table into this contract.

## Point-In-Time Rule

For each prediction timestamp, the alpha uses only curve rows with:

```text
curve.timestamp < prediction_timestamp
```

If `publication_timestamp` exists, it also requires:

```text
curve.publication_timestamp <= prediction_timestamp
```

No future prices, labels, simulator truth, or future curve revisions are used.

## Formula

For horizon `dt`, maturity `T`, par-adjusted spread `s_bar`, model par spread `s_hat`, and risky PV01 `Pi`:

```text
carry =
    c_prime * dt
    + (s_bar - c_prime) * (Pi(T) - Pi(T - dt))

rolldown =
    (s_hat(T) - s_hat(T - dt)) * Pi(T - dt)

relative_value =
    (s_bar - s_hat(T)) * Pi(T - dt)

total_return =
    carry + rolldown + relative_value
```

`c_prime` is coupon minus risk-free rate for bonds.

Positive values mean positive expected bond price contribution.

## Units

Default config assumes:

- spreads in basis points;
- `coupon_minus_riskfree` in percent;
- `risky_pv01` in price points per decimal spread unit;
- output in price points.

These are configurable.

## Missing Data

If the curve table is missing, no synthetic zeros are created.

The alpha returns `NaN` and a quality flag explaining the reason.

## Registry Status

`BOND_CARRY_ROLLDOWN` is implemented as the bond-native adapter.

The source-literal `FX_CARRY` and `FX_VALUE` entries remain separate because their original FX inputs and decisions are different.
