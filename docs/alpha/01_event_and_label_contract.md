# Event And Label Contract

This contract defines point-in-time event records and labels.

It does not implement predictive features.

## Canonical Side

The canonical side convention is customer perspective.

```text
customer buy  = +1
customer sell = -1
```

For an executed RFQ:

```text
dealer_inventory_change = -customer_side * executed_notional
```

This means a customer buy reduces dealer inventory.

TRACE side is not automatically trusted.

TRACE side must be observed from a documented source or separately validated by a classifier.

## Canonical Events

The code formalizes:

- `rfq_event`: inquiry, dealer response, firm-up, execution, expiry, and no-trade.
- `trace_trade`: executed TRACE print with explicit side quality.
- `composite_snapshot`: bid, ask, mid, spread, evaluated price, source, and quality flags.
- `reference_snapshot`: Treasury or swap curve, credit index, CDS, ETF, equity, volatility input.
- `security_master_snapshot`: bond identifier, issuer, sector, rating, maturity, duration, currency, seniority, type, callable, and convertible flags.

Each event keeps:

- source event time
- receive time
- effective time
- publication time
- revision time
- feature calculation time

Raw fields are not overwritten.

Adapters must document any transformation into these canonical fields.

## Point-In-Time Rule

All labels use as-of joins.

At prediction time `t`, the current fair value uses only rows with:

```text
effective_time <= t
publication_time <= t
revision_time <= t
```

At horizon end `t+h`, the future fair value uses only rows with:

```text
effective_time <= t+h
publication_time <= t+h
revision_time <= t+h
```

Later composite revisions do not rewrite historical labels.

Missing or stale future fair values produce censored labels.

They do not become zero returns.

## Labels

Clean-value labels:

```text
price_target_h = FV(t+h) - FV(t)
oas_price_equivalent_h = -effective_duration(t) * [OAS(t+h) - OAS(t)]
```

Event labels:

- next RFQ side
- next executed RFQ side
- next TRACE side when side is valid
- time to next event
- time to next meaningful fair-value move
- direction of first meaningful fair-value move

Aggressive labels:

```text
signed_move_j_h = customer_side_j * [FV(t_j+h) - FV(t_j)]
aggressive_j_h = 1 if signed_move_j_h exceeds the configured hurdle
```

Dealer markout:

```text
dealer_markout_j_h =
    sign(dealer_inventory_change_j) *
    [FV(t_j+h) - execution_price_j]
```

Dealer toxicity:

```text
dealer_toxic_j_h = 1 if dealer_markout_j_h < -cost_hurdle_h
```

RFQ decision labels are separate:

- responded
- firmed up
- won
- executed
- response latency
- quoted spread or price
- realized edge for won trades

The clean-value alpha target must not be trained only on won RFQs.

That would create quote-selection bias.

## Current Degradations

The local audit found TRACE prints.

It did not find real RFQ, composite, evaluated-price, or security-master tables.

So the label factory supports those tables, but tests use synthetic data.

TRACE side remains ambiguous until validated.

Signed TRACE labels must require side quality.

## Coverage

`label_coverage_report` summarizes label coverage by:

- bond
- issuer
- rating
- liquidity bucket
- horizon

